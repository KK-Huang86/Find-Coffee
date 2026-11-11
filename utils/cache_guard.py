import hashlib
import logging
import random
import re
import time
import unicodedata

from django.core.cache import cache

from utils.distributed_lock import DEFAULT_LOCK_TIMEOUT_SECONDS, distributed_lock

logger = logging.getLogger(__name__)

KEY_VERSION = 'v1'
# TTL 隨機係數範圍，避免同時寫入的 key 同時過期（防雪崩）
TTL_JITTER_RATIO = 0.1
# 拿不到鎖時每 POLL_INTERVAL 秒檢查一次快取，最多 WAIT_ATTEMPTS 次（約 2 秒）
DEFAULT_WAIT_ATTEMPTS = 20
DEFAULT_POLL_INTERVAL_SECONDS = 0.1

_MISS = object()


def normalize_text(text):
    """全形轉半形、去頭尾空白、連續空白合併、不分大小寫"""
    if not text:
        return ''
    text = unicodedata.normalize('NFKC', text)
    return re.sub(r'\s+', ' ', text).strip().casefold()


def make_key(namespace, raw):
    """以正規化後的內容雜湊組成 key，長度固定且不含特殊字元"""
    digest = hashlib.sha256(normalize_text(str(raw)).encode('utf-8')).hexdigest()[:32]
    return f'google:{KEY_VERSION}:{namespace}:{digest}'


def jittered_ttl(base_seconds):
    """TTL 乘上 0.9～1.1 的隨機係數，至少 1 秒"""
    if base_seconds <= 0:
        raise ValueError('TTL 必須大於 0')
    factor = random.uniform(1 - TTL_JITTER_RATIO, 1 + TTL_JITTER_RATIO)
    return max(1, round(base_seconds * factor))


def get_or_fetch(
    key,
    fetch,
    ttl,
    empty_ttl,
    lock_timeout=DEFAULT_LOCK_TIMEOUT_SECONDS,
    wait_attempts=DEFAULT_WAIT_ATTEMPTS,
    poll_interval=DEFAULT_POLL_INTERVAL_SECONDS,
):
    """
    Cache-aside，並處理穿透、擊穿、雪崩：

    - fetch() 回傳 (value, cacheable)；cacheable=False（暫時性錯誤）時不寫入快取
    - 空結果以 empty_ttl 快取（防穿透）
    - 未命中時以分散式鎖保護，同一個 key 同時只有一個請求 fetch；拿不到鎖的請求等待持有者寫入，
      逾時後自行 fetch（防擊穿，可用性優先）
    - TTL 加隨機偏移（防雪崩）
    """
    value = cache.get(key, _MISS)
    if value is not _MISS:
        return value

    with distributed_lock(f'cache:{key}', timeout=lock_timeout) as acquired:
        if acquired:
            # double check：前一個持有者可能剛寫入
            value = cache.get(key, _MISS)
            if value is not _MISS:
                return value
            return _fetch_and_store(key, fetch, ttl, empty_ttl)

    for _ in range(wait_attempts):
        time.sleep(poll_interval)
        value = cache.get(key, _MISS)
        if value is not _MISS:
            return value

    logger.warning(f'等待快取逾時，自行查詢: key={key}')
    return _fetch_and_store(key, fetch, ttl, empty_ttl)


def _fetch_and_store(key, fetch, ttl, empty_ttl):
    value, cacheable = fetch()
    if cacheable:
        cache.set(key, value, timeout=jittered_ttl(ttl if value else empty_ttl))
    return value
