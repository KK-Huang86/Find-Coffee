import logging
from datetime import timedelta

from django.utils import timezone

from cafe.tasks import refresh_cafe_data
from utils.utils import LockService

logger = logging.getLogger(__name__)

DATA_REFRESH_DAYS = 30
# 同一間店 TTL 內最多刷新一次；成功後 last_refreshed 已更新不會再進來，失敗時避免每次查詢都重打 Places Detail
REFRESH_LOCK_TTL_SECONDS = 600


def is_cafe_stale(cafe, now=None):
    """店家資料從未刷新，或距上次刷新已達 DATA_REFRESH_DAYS 天"""
    if cafe.last_refreshed is None:
        return True
    now = now or timezone.now()
    return now - cafe.last_refreshed >= timedelta(days=DATA_REFRESH_DAYS)


def refresh_cafe_now(cafe):
    """
    同步刷新店家資料，成功時 cafe 會重新從 DB 載入。

    S3 上傳不在這裡觸發，統一由請求流程的 FlexMessageBuilder.get_photo_url 觸發，避免同一次請求重複送出 task。

    Returns:
        bool: 是否成功刷新；取不到 lock、刷新失敗或發生例外皆回傳 False，呼叫端沿用既有資料
    """
    if not LockService.acquire(str(cafe.id), 'refresh', ttl=REFRESH_LOCK_TTL_SECONDS):
        logger.info(f'跳過刷新（{REFRESH_LOCK_TTL_SECONDS} 秒內已刷新或刷新中）: cafe_id={cafe.id}')
        return False

    try:
        result = refresh_cafe_data(cafe.id, trigger_photo_upload=False)
    except Exception as e:
        logger.error(f'同步刷新店家資料發生例外，沿用既有資料: cafe_id={cafe.id}, error={e}', exc_info=True)
        return False

    if not result or result.get('status') != 'success':
        logger.warning(f'同步刷新店家資料失敗，沿用既有資料: cafe_id={cafe.id}, result={result}')
        return False

    cafe.refresh_from_db()
    return True


def refresh_cafe_if_stale(cafe):
    """資料過期才同步刷新，回傳是否成功刷新"""
    if not is_cafe_stale(cafe):
        return False
    return refresh_cafe_now(cafe)
