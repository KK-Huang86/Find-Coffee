from pathlib import Path

import pytest

NGINX_CONF = Path(__file__).parent.parent / "nginx.conf"


@pytest.fixture
def conf():
    return NGINX_CONF.read_text()


class TestNoRealIpDirectives:
    def test_real_ip_header_absent(self, conf):
        assert "real_ip_header" not in conf

    def test_real_ip_recursive_absent(self, conf):
        assert "real_ip_recursive" not in conf

    def test_set_real_ip_from_absent(self, conf):
        assert "set_real_ip_from" not in conf


class TestCallbackExactMatch:
    def test_callback_uses_exact_match(self, conf):
        assert "location = /callback" in conf

    def test_callback_not_prefix_match(self, conf):
        assert "location /callback" not in conf


class TestXForwardedFor:
    def test_proxy_add_x_forwarded_for_absent(self, conf):
        assert "$proxy_add_x_forwarded_for" not in conf

    def test_x_forwarded_for_uses_remote_addr(self, conf):
        assert "X-Forwarded-For $remote_addr" in conf
