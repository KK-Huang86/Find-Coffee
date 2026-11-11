import logging
import zlib
from datetime import timedelta

from django.utils import timezone

from cafe.models import Cafe
from cafe.tasks import download_and_upload_cafe_photo, generate_cafe_ai_summary
from integrations.google.api import GoogleAPI
from utils.utils import LockService

logger = logging.getLogger(__name__)

DATA_REFRESH_DAYS = 30
# 過期門檻依 place_id 提前 0～REFRESH_JITTER_HOURS 小時，避免同一批匯入的店同一天一起過期（防快取雪崩）
REFRESH_JITTER_HOURS = 5 * 24
PHOTO_REFRESH_DAYS = 180
# 同一間店 TTL 內最多刷新一次；成功後 last_refreshed 已更新不會再進來，失敗時避免每次查詢都重打 Places Detail
REFRESH_LOCK_TTL_SECONDS = 600


def refresh_threshold(cafe):
    """
    店家資料的過期門檻，介於 DATA_REFRESH_DAYS - 5 天到 DATA_REFRESH_DAYS 天。

    依 place_id 決定而非每次隨機：同一間店門檻固定，不會這次判斷過期、下次又判斷未過期。
    只提前不延後，保證資料不會超過 DATA_REFRESH_DAYS 天未刷新。
    """
    base = timedelta(days=DATA_REFRESH_DAYS)
    if not cafe.place_id:
        return base
    jitter_hours = zlib.crc32(cafe.place_id.encode('utf-8')) % (REFRESH_JITTER_HOURS + 1)
    return base - timedelta(hours=jitter_hours)


def is_cafe_stale(cafe, now=None):
    """店家資料從未刷新，或距上次刷新已達自己的過期門檻"""
    if cafe.last_refreshed is None:
        return True
    now = now or timezone.now()
    return now - cafe.last_refreshed >= refresh_threshold(cafe)


def refresh_cafe_now(cafe):
    """
    同步向 Google 刷新店家資料，成功時 cafe 物件與 DB 皆為最新資料。

    - 同一間店 REFRESH_LOCK_TTL_SECONDS 內最多刷新一次
    - 刷新失敗或發生例外時記錄 log、回傳 False，cafe 維持原資料，呼叫端沿用既有資料回覆
    - 沒有 S3 照片時不在這裡觸發上傳，統一由 FlexMessageBuilder.get_photo_url 觸發，避免重複送出 task

    Returns:
        bool: 是否成功刷新
    """
    if not LockService.acquire(str(cafe.id), 'refresh', ttl=REFRESH_LOCK_TTL_SECONDS):
        logger.info(f'跳過刷新（{REFRESH_LOCK_TTL_SECONDS} 秒內已刷新或刷新中）: cafe_id={cafe.id}')
        return False

    try:
        result = GoogleAPI.get_shop_detail(cafe.place_id)
        if not result:
            logger.warning(f'Google API 無回傳資料，沿用既有資料: place_id={cafe.place_id}')
            return False
        old_reviews = cafe.reviews
        _apply_google_detail(cafe, result)
    except Exception as e:
        logger.error(f'同步刷新店家資料發生例外，沿用既有資料: place_id={cafe.place_id}, error={e}', exc_info=True)
        cafe.refresh_from_db()  # 丟掉已套用到記憶體但沒寫入成功的欄位
        return False

    # reviews 有變化，或先前尚未成功產生 ai_summary，重新觸發 AI 摘要產生（重試機會）
    reviews_changed = result.get('reviews') is not None and result.get('reviews') != old_reviews
    if reviews_changed or not cafe.ai_summary:
        generate_cafe_ai_summary.delay(cafe.id)

    _queue_photo_refresh_if_expired(cafe)

    logger.info(f'已同步刷新咖啡店資料: {cafe.name} ({cafe.place_id})')
    return True


def _apply_google_detail(cafe, result):
    """把 Places Detail 結果寫入 cafe；API 沒回傳（None）的欄位保留原值"""
    for field in (
        'name', 'address', 'phone', 'rating', 'user_ratings_total',
        'website', 'google_maps', 'photo_reference', 'reviews',
    ):
        value = result.get(field)
        if value is not None:
            setattr(cafe, field, value)

    cafe.last_refreshed = timezone.now()
    cafe.save()


def _queue_photo_refresh_if_expired(cafe):
    """
    S3 照片超過 PHOTO_REFRESH_DAYS 天時，以背景任務強制重新下載。

    不先清空舊的 photo_s3_url：新照片上傳完成前使用者仍看得到舊照片。
    """
    if not cafe.photo_s3_url or not cafe.photo_updated_at:
        return
    if timezone.now() - cafe.photo_updated_at < timedelta(days=PHOTO_REFRESH_DAYS):
        return
    logger.info(f'S3 照片超過 {PHOTO_REFRESH_DAYS} 天，背景重新下載: place_id={cafe.place_id}')
    download_and_upload_cafe_photo.delay(cafe.id, force=True)


def refresh_cafe_if_stale(cafe):
    """資料過期才同步刷新，回傳是否成功刷新"""
    if not is_cafe_stale(cafe):
        return False
    return refresh_cafe_now(cafe)


def refresh_photo_reference(place_id, old_reference):
    """
    Google 拒絕 photo_reference（多半是過期）時，同步刷新店家資料並回傳新的 reference

    Returns:
        str | None: 新的 reference；找不到店家、刷新被跳過或失敗、reference 未改變或為空時回傳 None
    """
    if not place_id:
        return None

    try:
        cafe = Cafe.objects.filter(place_id=place_id).first()
        if not cafe or not refresh_cafe_now(cafe):
            return None
    except Exception as e:
        logger.error(f'刷新 photo_reference 失敗 (place_id: {place_id}): {e}', exc_info=True)
        return None

    new_reference = cafe.photo_reference
    if not new_reference:
        logger.warning(f'刷新後店家沒有照片 reference (place_id: {place_id})')
        return None
    if new_reference == old_reference:
        logger.warning(f'刷新後 photo_reference 未改變，被拒原因非 reference 過期 (place_id: {place_id})')
        return None
    return new_reference
