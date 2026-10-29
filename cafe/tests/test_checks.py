import pytest
from django.core.management import call_command
from django.core.management.base import SystemCheckError

from cafe.checks import check_public_base_url


class TestPublicBaseUrlCheck:
    """正式環境的咖啡地圖連結不可為 localhost"""

    @pytest.mark.parametrize('url', [
        'http://localhost:8000',
        'http://127.0.0.1:8000/',
        'http://LOCALHOST',
        '',
    ])
    def test_production_with_local_url_warns(self, settings, url):
        settings.ENVIRONMENT = 'production'
        settings.PUBLIC_BASE_URL = url

        messages = check_public_base_url(None)

        assert [m.id for m in messages] == ['cafe.W001']

    def test_production_with_public_url_ok(self, settings):
        settings.ENVIRONMENT = 'production'
        settings.PUBLIC_BASE_URL = 'https://coffee.example.com'

        assert check_public_base_url(None) == []

    def test_development_with_localhost_ok(self, settings):
        settings.ENVIRONMENT = 'development'
        settings.PUBLIC_BASE_URL = 'http://localhost:8000'

        assert check_public_base_url(None) == []

    def test_registered_with_django_checks(self, settings):
        settings.ENVIRONMENT = 'production'
        settings.PUBLIC_BASE_URL = 'http://localhost:8000'

        with pytest.raises(SystemCheckError, match='cafe.W001'):
            call_command('check', '--fail-level', 'WARNING')
