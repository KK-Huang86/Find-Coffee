from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from cafe.services.favorite_map import request_favorite_map
from cafe.tests.factories import CafeFactory, FavoriteFactory, UserFactory

NOW = datetime(2026, 10, 27, 10, tzinfo=ZoneInfo('Asia/Taipei'))
UNKNOWN_TOKEN = 'A' * 43


@pytest.fixture(autouse=True)
def plain_static_storage(settings):
    # CI 以 core.settings 跑測試且不執行 collectstatic，manifest storage 會因找不到 manifest 而在 {% static %} 拋錯
    settings.STORAGES = {
        **settings.STORAGES,
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }


@pytest.fixture
def map_token(settings):
    settings.PUBLIC_BASE_URL = 'http://localhost:8000'
    user = UserFactory()
    FavoriteFactory(user=user, cafe=CafeFactory(name='祕密基地咖啡'))
    url = request_favorite_map(user, now=NOW).url
    return url.rstrip('/').rsplit('/', 1)[-1]


def page_url(token):
    return f'/map/{token}/'


def data_url(token):
    return f'/map/{token}/data.json'


def assert_security_headers(response):
    assert response['X-Robots-Tag'] == 'noindex'
    assert response['Referrer-Policy'] == 'strict-origin'
    csp = response['Content-Security-Policy']
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert 'https://tiles.openfreemap.org' in csp


@pytest.mark.django_db
class TestMapPage:
    """地圖頁面殼"""

    def test_valid_token_returns_html_without_personal_data(self, client, map_token):
        response = client.get(page_url(map_token))

        assert response.status_code == 200
        assert response['Content-Type'].startswith('text/html')
        html = response.content.decode()
        assert '祕密基地咖啡' not in html
        assert '<meta name="robots" content="noindex">' in html
        assert 'map-app.js' in html

    def test_security_headers(self, client, map_token):
        assert_security_headers(client.get(page_url(map_token)))

    def test_unknown_token_returns_404(self, client):
        assert client.get(page_url(UNKNOWN_TOKEN)).status_code == 404

    def test_post_not_allowed(self, client, map_token):
        assert client.post(page_url(map_token)).status_code == 405


@pytest.mark.django_db
class TestMapData:
    """地圖資料端點"""

    def test_valid_token_returns_snapshot(self, client, map_token):
        response = client.get(data_url(map_token))

        assert response.status_code == 200
        assert response['Content-Type'] == 'application/json'
        body = response.json()
        assert body['version'] == 1
        assert [c['name'] for c in body['cafes']] == ['祕密基地咖啡']

    def test_cache_control(self, client, map_token):
        cache_control = client.get(data_url(map_token))['Cache-Control']

        assert 'private' in cache_control
        assert 'max-age=60' in cache_control

    def test_security_headers(self, client, map_token):
        assert_security_headers(client.get(data_url(map_token)))

    def test_head_allowed(self, client, map_token):
        assert client.head(data_url(map_token)).status_code == 200

    @pytest.mark.parametrize('method', ['post', 'put', 'delete'])
    def test_write_methods_not_allowed(self, client, map_token, method):
        assert getattr(client, method)(data_url(map_token)).status_code == 405

    def test_unknown_token_returns_404(self, client):
        assert client.get(data_url(UNKNOWN_TOKEN)).status_code == 404

    @pytest.mark.parametrize('bad_token', [
        'short',
        'A' * 44,
        'A' * 42 + '!',
        'A' * 42 + '.',
        '%27%20OR%201%3D1--' + 'A' * 25,
    ])
    def test_malformed_token_same_404_without_db_query(self, client, django_assert_num_queries, bad_token):
        unknown = client.get(data_url(UNKNOWN_TOKEN))

        with django_assert_num_queries(0):
            response = client.get(data_url(bad_token))

        assert response.status_code == 404
        assert response.content == unknown.content

    def test_malformed_page_token_same_404(self, client):
        unknown = client.get(page_url(UNKNOWN_TOKEN))
        response = client.get(page_url('short'))

        assert response.status_code == 404
        assert response.content == unknown.content
