from django.core.cache import cache

class LockService:
    @staticmethod
    def acquire(user_id, action, ttl=2):
        """防止使用者短時間內重複觸發同一個動作"""

        key = f'ock:{user_id}:{action}'
        return cache.add(key, 1, timeout=ttl)  # SETNX + TTL