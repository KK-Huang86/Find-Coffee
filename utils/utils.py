from django.core.cache import cache

class LockService:
    DEFAULT_LOCK_TTL_SECONDS = 2
    @staticmethod
    def acquire(user_id, action, ttl=DEFAULT_LOCK_TTL_SECONDS):
        """防止使用者短時間內重複觸發同一個動作"""

        key = f'lock:{user_id}:{action}'
        return cache.add(key, 1, timeout=ttl)  # SETNX + TTL
