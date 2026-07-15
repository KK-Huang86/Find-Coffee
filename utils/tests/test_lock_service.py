from unittest.mock import patch

from django.core.cache import cache

from utils.utils import LockService


class TestLockService:
    """測試 LockService（Redis SETNX 防連點機制）"""

    def setup_method(self):
        cache.clear()

    def test_first_acquire_returns_true(self):
        """第一次取得鎖，回傳 True"""
        assert LockService.acquire('user1', 'postback') is True

    def test_second_acquire_same_key_returns_false(self):
        """相同 user_id + action，第二次取得鎖回傳 False"""
        LockService.acquire('user1', 'postback')
        assert LockService.acquire('user1', 'postback') is False

    def test_different_action_does_not_block(self):
        """相同 user_id，不同 action，互不影響"""
        LockService.acquire('user1', 'postback')
        assert LockService.acquire('user1', 'message') is True

    def test_different_user_does_not_block(self):
        """不同 user_id，相同 action，互不影響"""
        LockService.acquire('user1', 'postback')
        assert LockService.acquire('user2', 'postback') is True

    def test_default_ttl_is_2_seconds(self):
        """未指定 TTL 時，預設使用 2 秒"""
        with patch('utils.utils.cache.add') as mock_add:
            mock_add.return_value = True
            LockService.acquire('user1', 'postback')

        mock_add.assert_called_once_with('lock:user1:postback', 1, timeout=2)

    def test_custom_ttl_is_passed(self):
        """指定 ttl=1 時，正確傳入 cache.add"""
        with patch('utils.utils.cache.add') as mock_add:
            mock_add.return_value = True
            LockService.acquire('user1', 'vote_answer', ttl=1)

        mock_add.assert_called_once_with('lock:user1:vote_answer', 1, timeout=1)

    def test_lock_key_format(self):
        """lock key 格式為 lock:{user_id}:{action}"""
        with patch('utils.utils.cache.add') as mock_add:
            mock_add.return_value = True
            LockService.acquire('u123', 'my_action')

        key_used = mock_add.call_args[0][0]
        assert key_used == 'lock:u123:my_action'
