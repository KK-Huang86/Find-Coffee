import logging
import uuid
from contextlib import contextmanager

import redis
from django.conf import settings
from django.core.cache import cache
from redis.exceptions import LockError, RedisError

logger = logging.getLogger(__name__)

DEFAULT_LOCK_TIMEOUT_SECONDS = 10
# redis-py Lock 直接寫 Redis，不經過 Django cache 的 KEY_PREFIX，因此自行加上專案 prefix
REDIS_LOCK_KEY_PREFIX = 'linebot:lock'

_redis_client = None


def _get_redis_client():
    """快取後端為 Redis 時回傳 client；其他後端（測試的 LocMem）回傳 None"""
    global _redis_client
    default_cache = settings.CACHES['default']
    if not default_cache['BACKEND'].endswith('RedisCache'):
        return None
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(default_cache['LOCATION'])
    return _redis_client


@contextmanager
def distributed_lock(name, timeout=DEFAULT_LOCK_TIMEOUT_SECONDS):
    """
    非阻塞取得分散式鎖，yield 是否取得；離開時只釋放自己持有的鎖。

    - Redis 後端使用 redis-py Lock（token + Lua 比對後刪除）
    - 其他後端以 cache.add + token 比對刪除，比對與刪除非原子操作，僅供測試與沒有 Redis 的環境
    - 取得鎖時 Redis 錯誤：記錄 error，視同取得、不加鎖繼續執行（寧可多打一次外部 API，也不讓所有請求等待）
    """
    if not name:
        raise ValueError('lock name 不可為空')
    if timeout <= 0:
        raise ValueError('lock timeout 必須大於 0')

    client = _get_redis_client()
    if client is None:
        with _cache_lock(name, timeout) as acquired:
            yield acquired
        return

    lock = client.lock(f'{REDIS_LOCK_KEY_PREFIX}:{name}', timeout=timeout, blocking=False)
    try:
        acquired = lock.acquire()
    except RedisError as e:
        logger.error(f'取得分散式鎖失敗，不加鎖繼續執行: name={name}, error={e}', exc_info=True)
        yield True
        return

    try:
        yield acquired
    finally:
        if acquired:
            try:
                lock.release()
            except LockError as e:
                logger.warning(f'釋放分散式鎖時鎖已逾時或不屬於自己: name={name}, error={e}')


@contextmanager
def _cache_lock(name, timeout):
    key = f'lock:{name}'
    token = uuid.uuid4().hex
    acquired = cache.add(key, token, timeout=timeout)
    try:
        yield acquired
    finally:
        if acquired:
            if cache.get(key) == token:
                cache.delete(key)
            else:
                logger.warning(f'釋放分散式鎖時鎖已逾時或不屬於自己: name={name}')
