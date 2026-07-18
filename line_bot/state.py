from django.core.cache import cache
from line_bot.constants import UserState


class StateManager:
    """管理使用者狀態（Redis Cache）"""
    PREFIX = 'user_state'
    CONTEXT_PREFIX = 'user_context'
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

    @classmethod
    def get_context(cls, user_id):
        """取得使用者 context（用於多步驟流程）"""
        return cache.get(f'{cls.CONTEXT_PREFIX}:{user_id}', {})

    @classmethod
    def set_context(cls, user_id, context):
        """設定使用者 context"""
        cache.set(f'{cls.CONTEXT_PREFIX}:{user_id}', context, timeout=cls.TTL)

    @classmethod
    def clear_context(cls, user_id):
        """清除使用者 context"""
        cache.delete(f'{cls.CONTEXT_PREFIX}:{user_id}')

    @classmethod
    def reset_all(cls, user_id):
        """重置狀態和 context"""
        cls.reset_state(user_id)
        cls.clear_context(user_id)
