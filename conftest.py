import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def clear_cache():
    """測試使用 LocMemCache，lock / 暫停旗標會殘留在同一個 process，每個測試前後清空避免互相影響"""
    cache.clear()
    yield
    cache.clear()
