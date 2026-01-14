from django.core.cache import cache
from line_bot.constants import UserState


class StateManager:
    """管理使用者狀態（Redis Cache）"""
    PREFIX = 'user_state'
    TTL = 3600  # 1 小時過期

    @classmethod
    def get_state(cls, user_id):
        """取得使用者狀態"""
        return cache.get(f'{cls.PREFIX}:{user_id}', UserState.NORMAL)

    @classmethod
    def set_state(cls, user_id, state):
        """設定使用者狀態"""
        cache.set(f'{cls.PREFIX}:{user_id}', state, timeout=cls.TTL)

    @classmethod
    def reset_state(cls, user_id):
        """重置使用者狀態"""
        cache.delete(f'{cls.PREFIX}:{user_id}')
