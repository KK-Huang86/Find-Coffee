import logging
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache

from utils.cache_guard import get_or_fetch, jittered_ttl, make_key, normalize_text
from utils.distributed_lock import distributed_lock

KEY = 'google:v1:test:abc'


def _fetch_returning(value, cacheable=True):
    return MagicMock(return_value=(value, cacheable))


@pytest.fixture
def no_sleep():
    with patch('utils.cache_guard.time.sleep') as mock_sleep:
        yield mock_sleep


@pytest.fixture
def fixed_jitter():
    """隨機係數固定為 1.0，方便驗證 TTL"""
    with patch('utils.cache_guard.random.uniform', return_value=1.0):
        yield


class TestJitteredTtl:
    """測試 TTL 隨機偏移（防雪崩）"""

    def test_stays_within_ten_percent(self):
        """多次取樣都落在基準 TTL 的 90%～110%"""
        samples = [jittered_ttl(1000) for _ in range(200)]
        assert all(900 <= s <= 1100 for s in samples)

    def test_samples_are_spread(self):
        """取樣結果不會全部相同"""
        assert len({jittered_ttl(86400) for _ in range(50)}) > 1

    @pytest.mark.parametrize('factor, expected', [(0.9, 900), (1.1, 1100)])
    def test_boundaries(self, factor, expected):
        """隨機係數為上下限時的 TTL"""
        with patch('utils.cache_guard.random.uniform', return_value=factor):
            assert jittered_ttl(1000) == expected

    def test_returns_int(self):
        """回傳整數秒數"""
        assert isinstance(jittered_ttl(1000), int)

    def test_tiny_ttl_is_at_least_one_second(self):
        """基準 TTL 很小時，結果至少 1 秒（0 秒在部分後端代表不過期）"""
        with patch('utils.cache_guard.random.uniform', return_value=0.9):
            assert jittered_ttl(1) == 1

    @pytest.mark.parametrize('base', [0, -10])
    def test_non_positive_raises(self, base):
        """基準 TTL 必須大於 0"""
        with pytest.raises(ValueError):
            jittered_ttl(base)


class TestNormalizeText:
    """測試查詢文字正規化"""

    @pytest.mark.parametrize('raw', [
        'starbucks 信義',
        '  starbucks 信義  ',
        'Starbucks 信義',
        'STARBUCKS   信義',
        'ｓｔａｒｂｕｃｋｓ　信義',
        'starbucks\t信義\n',
    ])
    def test_equivalent_inputs_normalize_the_same(self, raw):
        """全形半形、頭尾空白、連續空白、大小寫不同時結果相同"""
        assert normalize_text(raw) == 'starbucks 信義'

    @pytest.mark.parametrize('raw', [None, '', '   '])
    def test_empty_inputs_return_empty_string(self, raw):
        """空值回傳空字串"""
        assert normalize_text(raw) == ''


class TestMakeKey:
    """測試快取 key 組成"""

    def test_equivalent_inputs_share_key(self):
        """正規化後相同的輸入得到相同 key"""
        assert make_key('textsearch', ' Starbucks  信義 ') == make_key('textsearch', 'starbucks 信義')

    def test_different_inputs_have_different_keys(self):
        """不同查詢得到不同 key"""
        assert make_key('textsearch', '星巴克') != make_key('textsearch', '路易莎')

    def test_namespace_separates_keys(self):
        """相同文字在不同 namespace 下 key 不同"""
        assert make_key('textsearch', '台北') != make_key('geocode', '台北')

    def test_key_is_versioned_and_namespaced(self):
        """key 帶版本與 namespace，之後改格式只要換版本"""
        assert make_key('geocode', '台北').startswith('google:v1:geocode:')

    def test_long_input_has_bounded_length(self):
        """超長輸入的 key 長度固定，不會超過 Redis / memcached key 限制"""
        short_key = make_key('textsearch', 'a')
        long_key = make_key('textsearch', 'a' * 10000)
        assert len(long_key) == len(short_key)
        assert len(long_key) < 100


class TestGetOrFetch:
    """測試 cache-aside 流程：穿透、擊穿、雪崩防護"""

    def test_hit_does_not_fetch(self):
        """快取命中時不呼叫 fetch"""
        cache.set(KEY, ['cached'])
        fetch = _fetch_returning(['fresh'])

        assert get_or_fetch(KEY, fetch, ttl=100, empty_ttl=10) == ['cached']
        fetch.assert_not_called()

    @pytest.mark.parametrize('empty_value', [[], {}])
    def test_cached_empty_result_is_a_hit(self, empty_value):
        """快取的空結果也算命中（防穿透），不會被當成未命中"""
        cache.set(KEY, empty_value)
        fetch = _fetch_returning(['fresh'])

        assert get_or_fetch(KEY, fetch, ttl=100, empty_ttl=10) == empty_value
        fetch.assert_not_called()

    def test_miss_fetches_and_stores(self, fixed_jitter):
        """未命中時呼叫 fetch 一次並寫入快取"""
        fetch = _fetch_returning(['fresh'])

        with patch('utils.cache_guard.cache.set', wraps=cache.set) as mock_set:
            assert get_or_fetch(KEY, fetch, ttl=100, empty_ttl=10) == ['fresh']

        fetch.assert_called_once_with()
        assert cache.get(KEY) == ['fresh']
        assert mock_set.call_args.kwargs['timeout'] == 100

    def test_second_call_hits_cache(self):
        """第二次呼叫命中快取，fetch 只被呼叫一次"""
        fetch = _fetch_returning(['fresh'])

        get_or_fetch(KEY, fetch, ttl=100, empty_ttl=10)
        get_or_fetch(KEY, fetch, ttl=100, empty_ttl=10)

        assert fetch.call_count == 1

    @pytest.mark.parametrize('empty_value', [[], {}, None])
    def test_empty_result_uses_short_ttl(self, fixed_jitter, empty_value):
        """確定的空結果以 empty_ttl 快取（防穿透）"""
        fetch = _fetch_returning(empty_value)

        with patch('utils.cache_guard.cache.set') as mock_set:
            get_or_fetch(KEY, fetch, ttl=100, empty_ttl=10)

        assert mock_set.call_args.kwargs['timeout'] == 10

    def test_ttl_is_jittered(self):
        """寫入快取的 TTL 經過隨機偏移（防雪崩）"""
        fetch = _fetch_returning(['fresh'])

        with patch('utils.cache_guard.random.uniform', return_value=1.1), \
             patch('utils.cache_guard.cache.set') as mock_set:
            get_or_fetch(KEY, fetch, ttl=1000, empty_ttl=10)

        assert mock_set.call_args.kwargs['timeout'] == 1100

    def test_not_cacheable_result_is_not_stored(self):
        """暫時性錯誤（cacheable=False）不寫入快取，下次重新 fetch"""
        fetch = _fetch_returning([], cacheable=False)

        assert get_or_fetch(KEY, fetch, ttl=100, empty_ttl=10) == []
        get_or_fetch(KEY, fetch, ttl=100, empty_ttl=10)

        assert cache.get(KEY, 'MISSING') == 'MISSING'
        assert fetch.call_count == 2

    def test_fetch_exception_propagates_and_releases_lock(self):
        """fetch 拋出例外時不寫入快取、例外往外拋，且鎖被釋放"""
        fetch = MagicMock(side_effect=RuntimeError('boom'))

        with pytest.raises(RuntimeError):
            get_or_fetch(KEY, fetch, ttl=100, empty_ttl=10)

        assert cache.get(KEY, 'MISSING') == 'MISSING'
        with distributed_lock(f'cache:{KEY}') as acquired:
            assert acquired is True

    def test_double_check_after_acquiring_lock(self):
        """取得鎖時前一個持有者剛寫入快取，直接回傳快取，不 fetch"""
        fetch = _fetch_returning(['fresh'])

        @contextmanager
        def lock_after_other_holder_finished(name, timeout=10):
            cache.set(KEY, ['written by previous holder'])
            yield True

        with patch('utils.cache_guard.distributed_lock', side_effect=lock_after_other_holder_finished):
            result = get_or_fetch(KEY, fetch, ttl=100, empty_ttl=10)

        assert result == ['written by previous holder']
        fetch.assert_not_called()

    def test_waits_for_holder_and_returns_its_result(self, no_sleep):
        """鎖被他人持有時等待，持有者寫入後回傳該結果，不 fetch（防擊穿）"""
        fetch = _fetch_returning(['fresh'])
        polls = []

        def holder_finishes_on_third_poll(_seconds):
            polls.append(_seconds)
            if len(polls) == 3:
                cache.set(KEY, ['from holder'])

        no_sleep.side_effect = holder_finishes_on_third_poll

        with distributed_lock(f'cache:{KEY}'):
            result = get_or_fetch(KEY, fetch, ttl=100, empty_ttl=10, wait_attempts=20, poll_interval=0.1)

        assert result == ['from holder']
        fetch.assert_not_called()
        assert polls == [0.1, 0.1, 0.1]

    def test_wait_timeout_fetches_itself(self, no_sleep, caplog):
        """等待逾時後自行 fetch 並寫入快取，記錄 warning（可用性優先）"""
        fetch = _fetch_returning(['fresh'])

        with caplog.at_level(logging.WARNING), distributed_lock(f'cache:{KEY}'):
            result = get_or_fetch(KEY, fetch, ttl=100, empty_ttl=10, wait_attempts=5, poll_interval=0.1)

        assert result == ['fresh']
        fetch.assert_called_once_with()
        assert no_sleep.call_count == 5
        assert cache.get(KEY) == ['fresh']
        assert KEY in caplog.text

    def test_wait_returns_cached_empty_result(self, no_sleep):
        """等待期間持有者寫入空結果，也視為命中"""
        fetch = _fetch_returning(['fresh'])
        no_sleep.side_effect = lambda _s: cache.set(KEY, [])

        with distributed_lock(f'cache:{KEY}'):
            result = get_or_fetch(KEY, fetch, ttl=100, empty_ttl=10)

        assert result == []
        fetch.assert_not_called()

    def test_lock_uses_given_timeout(self):
        """鎖的逾時可由呼叫端指定"""
        fetch = _fetch_returning(['fresh'])

        with patch('utils.cache_guard.distributed_lock', wraps=distributed_lock) as mock_lock:
            get_or_fetch(KEY, fetch, ttl=100, empty_ttl=10, lock_timeout=15)

        mock_lock.assert_called_once_with(f'cache:{KEY}', timeout=15)
