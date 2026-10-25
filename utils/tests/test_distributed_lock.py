import logging
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from redis.exceptions import LockError, RedisError

from utils.distributed_lock import distributed_lock


class TestDistributedLockCacheBackend:
    """非 Redis 快取後端（測試的 LocMem）：以 cache.add + token 實作"""

    def test_acquires_free_lock_and_releases_on_exit(self):
        """未被持有的鎖可以取得，離開後可以再次取得"""
        with distributed_lock('cafe:abc') as acquired:
            assert acquired is True

        with distributed_lock('cafe:abc') as acquired_again:
            assert acquired_again is True

    def test_held_lock_returns_false_immediately(self):
        """鎖已被持有時立即回報未取得"""
        with distributed_lock('cafe:abc') as outer:
            with distributed_lock('cafe:abc') as inner:
                assert outer is True
                assert inner is False

    def test_not_acquired_does_not_release_holder_lock(self):
        """沒取得鎖的一方離開時，不會釋放持有者的鎖"""
        with distributed_lock('cafe:abc'):
            with distributed_lock('cafe:abc'):
                pass
            with distributed_lock('cafe:abc') as third:
                assert third is False

    def test_different_names_are_independent(self):
        """不同名稱的鎖互不影響"""
        with distributed_lock('cafe:abc') as first:
            with distributed_lock('cafe:xyz') as second:
                assert first is True
                assert second is True

    def test_releases_when_body_raises(self):
        """持有期間拋出例外時仍釋放鎖，例外照常往外拋"""
        with pytest.raises(RuntimeError):
            with distributed_lock('cafe:abc'):
                raise RuntimeError('boom')

        with distributed_lock('cafe:abc') as acquired:
            assert acquired is True

    def test_does_not_delete_lock_taken_by_others_after_expiry(self, caplog):
        """鎖逾時後被他人取得，原持有者釋放時不刪除他人的鎖，並記錄 warning"""
        with caplog.at_level(logging.WARNING):
            with distributed_lock('cafe:abc'):
                # 模擬自己的鎖已逾時，另一個請求取得同一把鎖
                cache.set('lock:cafe:abc', 'other-token', timeout=30)

        assert cache.get('lock:cafe:abc') == 'other-token'
        assert 'cafe:abc' in caplog.text

    def test_passes_timeout_to_cache(self):
        """鎖的逾時傳給快取，持有者當機時自動釋放"""
        with patch('utils.distributed_lock.cache.add', return_value=True) as mock_add:
            with distributed_lock('cafe:abc', timeout=7):
                pass

        assert mock_add.call_args.kwargs['timeout'] == 7

    @pytest.mark.parametrize('name', ['', None])
    def test_empty_name_raises(self, name):
        """名稱為空時拋出 ValueError，避免所有呼叫端共用同一把鎖"""
        with pytest.raises(ValueError):
            with distributed_lock(name):
                pass

    @pytest.mark.parametrize('timeout', [0, -1])
    def test_non_positive_timeout_raises(self, timeout):
        """逾時必須大於 0，否則鎖永遠不會自動釋放或立即失效"""
        with pytest.raises(ValueError):
            with distributed_lock('cafe:abc', timeout=timeout):
                pass


class TestDistributedLockRedisBackend:
    """Redis 後端：使用 redis-py Lock（token + Lua 釋放）"""

    def _mock_client(self, acquire_result=True):
        mock_lock = MagicMock()
        mock_lock.acquire.return_value = acquire_result
        mock_client = MagicMock()
        mock_client.lock.return_value = mock_lock
        return mock_client, mock_lock

    def test_uses_redis_lock_non_blocking_with_timeout(self):
        """以非阻塞方式取得 redis-py Lock，帶入逾時與帶 prefix 的 key"""
        mock_client, mock_lock = self._mock_client()

        with patch('utils.distributed_lock._get_redis_client', return_value=mock_client):
            with distributed_lock('cafe:abc', timeout=10) as acquired:
                assert acquired is True

        mock_client.lock.assert_called_once_with('linebot:lock:cafe:abc', timeout=10, blocking=False)
        mock_lock.acquire.assert_called_once_with()
        mock_lock.release.assert_called_once_with()

    def test_not_acquired_does_not_release(self):
        """沒取得鎖時不呼叫 release"""
        mock_client, mock_lock = self._mock_client(acquire_result=False)

        with patch('utils.distributed_lock._get_redis_client', return_value=mock_client):
            with distributed_lock('cafe:abc') as acquired:
                assert acquired is False

        mock_lock.release.assert_not_called()

    def test_release_lock_error_logs_warning_without_raising(self, caplog):
        """鎖已逾時（LockError）時記錄 warning，不往外拋"""
        mock_client, mock_lock = self._mock_client()
        mock_lock.release.side_effect = LockError('expired')

        with caplog.at_level(logging.WARNING), \
             patch('utils.distributed_lock._get_redis_client', return_value=mock_client):
            with distributed_lock('cafe:abc'):
                pass

        assert 'cafe:abc' in caplog.text

    def test_redis_error_on_acquire_proceeds_without_lock(self, caplog):
        """取得鎖時 Redis 錯誤：記錄 error，視同取得繼續執行，不呼叫 release"""
        mock_client, mock_lock = self._mock_client()
        mock_lock.acquire.side_effect = RedisError('connection refused')

        with caplog.at_level(logging.ERROR), \
             patch('utils.distributed_lock._get_redis_client', return_value=mock_client):
            with distributed_lock('cafe:abc') as acquired:
                assert acquired is True

        mock_lock.release.assert_not_called()
        assert any(r.levelno == logging.ERROR for r in caplog.records)

    def test_releases_when_body_raises(self):
        """持有期間拋出例外時仍釋放，例外照常往外拋"""
        mock_client, mock_lock = self._mock_client()

        with patch('utils.distributed_lock._get_redis_client', return_value=mock_client):
            with pytest.raises(RuntimeError):
                with distributed_lock('cafe:abc'):
                    raise RuntimeError('boom')

        mock_lock.release.assert_called_once_with()
