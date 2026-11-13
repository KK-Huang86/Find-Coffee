"""
個人咖啡地圖：依使用者收藏生成 snapshot，並以冷卻時間與每日次數控制重新生成（見 favorite-cafe-map change）
"""
import hashlib
import logging
import math
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from cafe.models import FavoriteMap
from utils.phone import build_tel_uri

logger = logging.getLogger(__name__)

TAIPEI_TZ = ZoneInfo('Asia/Taipei')
SNAPSHOT_VERSION = 1
COOLDOWN = timedelta(minutes=30)
DAILY_LIMIT = 5
TOKEN_BYTES = 32
TOKEN_MAX_ATTEMPTS = 3
MAX_WRITE_ATTEMPTS = 2
SLOW_GENERATION_SECONDS = 1.0
ATTRIBUTE_FIELDS = ('has_socket', 'limited_time', 'pet_friendly', 'has_pet')


@dataclass(frozen=True)
class FavoriteMapResult:
    """status: no_favorites / created / generated / unchanged / cooldown / daily_limit / error"""
    status: str
    url: str | None
    wait_minutes: int | None = None


def request_favorite_map(user, *, now: datetime | None = None) -> FavoriteMapResult:
    """
    使用者點選「我的咖啡地圖」時呼叫，回傳地圖連結與本次處理結果

    並發防護採條件式 UPDATE（樂觀鎖）：寫入時比對讀取當下的 fingerprint 與生成時間，
    被其他請求搶先寫入時不重複生成、不重複計次
    """
    now = now or timezone.now()
    try:
        favorite_map = FavoriteMap.objects.filter(user=user).first()
        if favorite_map is None:
            return _create_map(user, now)
        return _refresh_map(user, favorite_map, now)
    except Exception:
        logger.exception(f'咖啡地圖生成失敗 (user_pk: {user.pk})')
        return FavoriteMapResult(status='error', url=None)


def get_map_snapshot(token: str) -> dict | None:
    """依 token 取得 snapshot；token 不存在時回傳 None"""
    return FavoriteMap.objects.filter(token=token).values_list('snapshot', flat=True).first()


def build_snapshot(user, *, now: datetime) -> dict:
    """組出使用者收藏的 snapshot；缺座標的店家排除，依收藏時間由新到舊"""
    favorites = (
        user.favorites
        .select_related('cafe')
        .filter(cafe__lat__isnull=False, cafe__lng__isnull=False)
        .order_by('-created_at')
    )
    return {
        'version': SNAPSHOT_VERSION,
        'generated_at': _taipei_iso(now),
        'cafes': [_serialize_favorite(favorite) for favorite in favorites],
    }


def _create_map(user, now) -> FavoriteMapResult:
    if not user.favorites.exists():
        return FavoriteMapResult(status='no_favorites', url=None)

    fingerprint = _fingerprint(user)
    snapshot = _timed_build_snapshot(user, now)
    # token 唯一性交給 unique constraint：撞號時換新 token 重試，撞到 user 則代表並發建立
    for _ in range(TOKEN_MAX_ATTEMPTS):
        token = secrets.token_urlsafe(TOKEN_BYTES)
        try:
            # savepoint：撞到 unique constraint 時不影響外層 transaction
            with transaction.atomic():
                favorite_map = FavoriteMap.objects.create(
                    user=user,
                    token=token,
                    snapshot=snapshot,
                    fingerprint=fingerprint,
                    generated_at=now,
                    daily_count=1,
                    daily_count_date=_taipei_date(now),
                )
        except IntegrityError:
            existing = FavoriteMap.objects.filter(user=user).first()
            if existing is not None:
                logger.info(f'咖啡地圖已由並發請求建立 (user_pk: {user.pk})')
                return _refresh_map(user, existing, now)
            logger.warning(f'咖啡地圖 token 重複，重新產生 (user_pk: {user.pk})')
            continue

        logger.info(f'咖啡地圖建立 (user_pk: {user.pk}, cafes: {len(snapshot["cafes"])})')
        return FavoriteMapResult(status='created', url=_build_url(favorite_map.token))

    raise RuntimeError(f'咖啡地圖 token 連續 {TOKEN_MAX_ATTEMPTS} 次重複')


def _refresh_map(user, favorite_map, now) -> FavoriteMapResult:
    url = _build_url(favorite_map.token)
    fingerprint = _fingerprint(user)

    # 被並發請求搶先寫入時以最新狀態重新判斷；連續輸掉超過上限就放棄，避免回報錯誤的「未變動」
    for _ in range(MAX_WRITE_ATTEMPTS):
        result = _evaluate(favorite_map, fingerprint, url, now)
        if result is not None:
            return result

        today = _taipei_date(now)
        used_today = favorite_map.daily_count if favorite_map.daily_count_date == today else 0
        snapshot = _timed_build_snapshot(user, now)
        updated = FavoriteMap.objects.filter(
            pk=favorite_map.pk,
            fingerprint=favorite_map.fingerprint,
            generated_at=favorite_map.generated_at,
        ).update(
            snapshot=snapshot,
            fingerprint=fingerprint,
            generated_at=now,
            daily_count=used_today + 1,
            daily_count_date=today,
            updated_at=timezone.now(),
        )
        if updated:
            logger.info(
                f'咖啡地圖更新 (user_pk: {user.pk}, cafes: {len(snapshot["cafes"])}, today: {used_today + 1})'
            )
            return FavoriteMapResult(status='generated', url=url)

        logger.info(f'咖啡地圖已由並發請求更新 (user_pk: {user.pk})')
        favorite_map = FavoriteMap.objects.get(pk=favorite_map.pk)
        fingerprint = _fingerprint(user)

    raise RuntimeError(f'咖啡地圖連續 {MAX_WRITE_ATTEMPTS} 次被並發請求搶先寫入')


def _evaluate(favorite_map, fingerprint, url, now) -> FavoriteMapResult | None:
    """依目前狀態判斷結果；需要生成新版時回傳 None"""
    if fingerprint == favorite_map.fingerprint:
        return FavoriteMapResult(status='unchanged', url=url)

    # 先判斷每日上限：已用完時不讓使用者白等冷卻
    used_today = favorite_map.daily_count if favorite_map.daily_count_date == _taipei_date(now) else 0
    if used_today >= DAILY_LIMIT:
        return FavoriteMapResult(status='daily_limit', url=url)

    remaining = favorite_map.generated_at + COOLDOWN - now
    if remaining > timedelta(0):
        wait_minutes = max(1, math.ceil(remaining.total_seconds() / 60))
        return FavoriteMapResult(status='cooldown', url=url, wait_minutes=wait_minutes)
    return None


def _timed_build_snapshot(user, now) -> dict:
    started = time.monotonic()
    snapshot = build_snapshot(user, now=now)
    elapsed = time.monotonic() - started
    if elapsed > SLOW_GENERATION_SECONDS:
        logger.warning(f'咖啡地圖 snapshot 生成過慢 (user_pk: {user.pk}, seconds: {elapsed:.2f})')
    return snapshot


def _fingerprint(user) -> str:
    cafe_ids = sorted(user.favorites.values_list('cafe_id', flat=True))
    return hashlib.sha256(','.join(str(cafe_id) for cafe_id in cafe_ids).encode()).hexdigest()


def _build_url(token: str) -> str:
    return f'{settings.PUBLIC_BASE_URL.rstrip("/")}/map/{token}/'


def _taipei_date(now):
    return now.astimezone(TAIPEI_TZ).date()


def _taipei_iso(value: datetime) -> str:
    return value.astimezone(TAIPEI_TZ).isoformat()


def _blank_to_none(value):
    if isinstance(value, str):
        value = value.strip()
    return value or None


def _serialize_favorite(favorite) -> dict:
    cafe = favorite.cafe
    tel_uri = build_tel_uri(cafe.phone)
    return {
        'place_id': cafe.place_id,
        'name': cafe.name,
        'address': cafe.address,
        'lat': float(cafe.lat),
        'lng': float(cafe.lng),
        'rating': float(cafe.rating) if cafe.rating is not None else None,
        'user_ratings_total': cafe.user_ratings_total,
        # 佔位字串（如「無提供」）無法撥號，視為缺值
        'phone': cafe.phone if tel_uri else None,
        'tel_uri': tel_uri,
        'google_maps': _blank_to_none(cafe.google_maps),
        'website': _blank_to_none(cafe.website),
        'photo_url': _blank_to_none(cafe.photo_s3_url),
        'ai_summary': _blank_to_none(cafe.ai_summary),
        'attributes': {field: _blank_to_none(getattr(cafe, field)) for field in ATTRIBUTE_FIELDS},
        'note': _blank_to_none(favorite.note),
        'favorited_at': _taipei_iso(favorite.created_at),
    }
