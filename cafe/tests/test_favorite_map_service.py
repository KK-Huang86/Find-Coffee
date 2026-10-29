import json
import logging
import re
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from cafe.services import favorite_map
from cafe.services.favorite_map import build_snapshot, get_map_snapshot, request_favorite_map
from cafe.tests.factories import CafeFactory, FavoriteFactory, UserFactory

TPE = ZoneInfo('Asia/Taipei')
TOKEN_PATTERN = re.compile(r'^[A-Za-z0-9_-]+$')


def tpe(year, month, day, hour, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=TPE)


def token_of(url):
    return url.rstrip('/').rsplit('/', 1)[-1]


def favorite_new_cafe(user):
    return FavoriteFactory(user=user, cafe=CafeFactory())


def cafe_count(result):
    return len(get_map_snapshot(token_of(result.url))['cafes'])


@pytest.fixture(autouse=True)
def public_base_url(settings):
    settings.PUBLIC_BASE_URL = 'http://localhost:8000'


@pytest.mark.django_db
class TestMapToken:
    """地圖存取 token"""

    def test_first_request_creates_map_with_token(self):
        user = UserFactory()
        favorite_new_cafe(user)

        result = request_favorite_map(user, now=tpe(2026, 10, 27, 10))

        assert result.status == 'created'
        token = token_of(result.url)
        assert len(token) >= 32
        assert TOKEN_PATTERN.match(token)

    def test_token_does_not_contain_line_user_id(self):
        user = UserFactory(line_user_id='U1234567890abcdef1234567890abcdef')
        favorite_new_cafe(user)

        token = token_of(request_favorite_map(user, now=tpe(2026, 10, 27, 10)).url)

        line_id = user.line_user_id
        for i in range(len(line_id) - 7):
            assert line_id[i:i + 8] not in token

    def test_tokens_are_unique_between_users(self):
        users = [UserFactory() for _ in range(5)]
        for user in users:
            favorite_new_cafe(user)

        tokens = {token_of(request_favorite_map(u, now=tpe(2026, 10, 27, 10)).url) for u in users}

        assert len(tokens) == 5

    def test_token_unchanged_on_later_requests(self):
        user = UserFactory()
        favorite_new_cafe(user)
        first = request_favorite_map(user, now=tpe(2026, 10, 27, 10))

        favorite_new_cafe(user)
        second = request_favorite_map(user, now=tpe(2026, 10, 27, 11))

        assert second.status == 'generated'
        assert second.url == first.url

    def test_token_collision_retries_with_new_token(self):
        other = UserFactory()
        favorite_new_cafe(other)
        taken = token_of(request_favorite_map(other, now=tpe(2026, 10, 27, 10)).url)
        fresh = 'B' * 43
        user = UserFactory()
        favorite_new_cafe(user)

        with patch('cafe.services.favorite_map.secrets.token_urlsafe', side_effect=[taken, fresh]):
            result = request_favorite_map(user, now=tpe(2026, 10, 27, 10))

        assert result.status == 'created'
        assert token_of(result.url) == fresh

    def test_token_collision_gives_up_after_three_attempts(self, caplog):
        other = UserFactory()
        favorite_new_cafe(other)
        taken = token_of(request_favorite_map(other, now=tpe(2026, 10, 27, 10)).url)
        user = UserFactory()
        favorite_new_cafe(user)

        with patch('cafe.services.favorite_map.secrets.token_urlsafe', return_value=taken) as mock_token, \
                caplog.at_level(logging.ERROR):
            result = request_favorite_map(user, now=tpe(2026, 10, 27, 10))

        assert result.status == 'error'
        assert result.url is None
        assert mock_token.call_count == 3
        assert caplog.records

    def test_token_collision_at_insert_retries(self):
        """token 只在寫入時由 unique constraint 檢查；撞號時換新 token 重試，不當成並發建立"""
        other = UserFactory()
        favorite_new_cafe(other)
        taken = token_of(request_favorite_map(other, now=tpe(2026, 10, 27, 10)).url)
        fresh = 'C' * 43
        user = UserFactory()
        favorite_new_cafe(user)

        with patch('cafe.services.favorite_map.secrets.token_urlsafe', side_effect=[taken, taken, fresh]):
            result = request_favorite_map(user, now=tpe(2026, 10, 27, 10))

        assert result.status == 'created'
        assert token_of(result.url) == fresh

    def test_map_deleted_with_user(self):
        user = UserFactory()
        favorite_new_cafe(user)
        token = token_of(request_favorite_map(user, now=tpe(2026, 10, 27, 10)).url)

        user.delete()

        assert get_map_snapshot(token) is None


@pytest.mark.django_db
class TestMapUrl:
    """地圖連結格式"""

    def test_url_format(self):
        user = UserFactory()
        favorite_new_cafe(user)

        url = request_favorite_map(user, now=tpe(2026, 10, 27, 10)).url

        assert re.match(r'^http://localhost:8000/map/[A-Za-z0-9_-]+/$', url)

    def test_trailing_slash_in_base_url_is_normalized(self, settings):
        settings.PUBLIC_BASE_URL = 'https://example.com/'
        user = UserFactory()
        favorite_new_cafe(user)

        url = request_favorite_map(user, now=tpe(2026, 10, 27, 10)).url

        assert url.startswith('https://example.com/map/')
        assert '//map' not in url


@pytest.mark.django_db
class TestChangeDetection:
    """收藏變動判斷：冷卻已過時，只有收藏集合變動才會生成新版"""

    def test_unchanged_favorites_return_existing_link(self):
        user = UserFactory()
        favorite_new_cafe(user)
        first = request_favorite_map(user, now=tpe(2026, 10, 27, 10))

        result = request_favorite_map(user, now=tpe(2026, 10, 27, 11))

        assert result.status == 'unchanged'
        assert result.url == first.url

    def test_added_favorite_is_a_change(self):
        user = UserFactory()
        favorite_new_cafe(user)
        request_favorite_map(user, now=tpe(2026, 10, 27, 10))

        favorite_new_cafe(user)
        result = request_favorite_map(user, now=tpe(2026, 10, 27, 11))

        assert result.status == 'generated'
        assert cafe_count(result) == 2

    def test_removed_favorite_is_a_change(self):
        user = UserFactory()
        favorite_new_cafe(user)
        removed = favorite_new_cafe(user)
        request_favorite_map(user, now=tpe(2026, 10, 27, 10))

        removed.delete()
        result = request_favorite_map(user, now=tpe(2026, 10, 27, 11))

        assert result.status == 'generated'
        assert cafe_count(result) == 1

    def test_remove_then_re_add_same_cafe_is_unchanged(self):
        user = UserFactory()
        favorite = favorite_new_cafe(user)
        request_favorite_map(user, now=tpe(2026, 10, 27, 10))

        cafe = favorite.cafe
        favorite.delete()
        FavoriteFactory(user=user, cafe=cafe)
        result = request_favorite_map(user, now=tpe(2026, 10, 27, 11))

        assert result.status == 'unchanged'

    def test_cafe_data_update_is_not_a_change(self):
        user = UserFactory()
        favorite = favorite_new_cafe(user)
        first = request_favorite_map(user, now=tpe(2026, 10, 27, 10))

        cafe = favorite.cafe
        cafe.ai_summary = '新的摘要'
        cafe.photo_s3_url = 'https://cdn.example.com/new.jpg'
        cafe.has_socket = 'yes'
        cafe.save()
        result = request_favorite_map(user, now=tpe(2026, 10, 27, 11))

        assert result.status == 'unchanged'
        assert get_map_snapshot(token_of(first.url))['cafes'][0]['ai_summary'] is None


@pytest.mark.django_db
class TestGenerationRules:
    """地圖生成規則"""

    def test_no_favorites_and_no_map(self):
        user = UserFactory()

        result = request_favorite_map(user, now=tpe(2026, 10, 27, 10))

        assert result.status == 'no_favorites'
        assert result.url is None
        # 之後加了收藏才第一次建立
        favorite_new_cafe(user)
        assert request_favorite_map(user, now=tpe(2026, 10, 27, 10, 1)).status == 'created'

    def test_all_favorites_removed_generates_empty_map(self):
        user = UserFactory()
        favorite = favorite_new_cafe(user)
        request_favorite_map(user, now=tpe(2026, 10, 27, 10))

        favorite.delete()
        result = request_favorite_map(user, now=tpe(2026, 10, 27, 11))

        assert result.status == 'generated'
        assert cafe_count(result) == 0

    def test_unchanged_requests_do_not_count(self):
        user = UserFactory()
        favorite_new_cafe(user)
        start = tpe(2026, 10, 27, 9)
        request_favorite_map(user, now=start)  # 第 1 次
        for i in range(10):
            assert request_favorite_map(user, now=start + timedelta(minutes=i)).status == 'unchanged'

        # 未計次，所以還能再生成 4 次
        for i in range(1, 5):
            favorite_new_cafe(user)
            assert request_favorite_map(user, now=start + timedelta(minutes=30 * i)).status == 'generated'
        favorite_new_cafe(user)
        assert request_favorite_map(user, now=start + timedelta(minutes=150)).status == 'daily_limit'

    def test_cooldown_returns_existing_link_with_remaining_minutes(self):
        user = UserFactory()
        favorite_new_cafe(user)
        first = request_favorite_map(user, now=tpe(2026, 10, 27, 10))

        favorite_new_cafe(user)
        result = request_favorite_map(user, now=tpe(2026, 10, 27, 10, 12))

        assert result.status == 'cooldown'
        assert result.wait_minutes == 18
        assert result.url == first.url
        assert cafe_count(result) == 1

    def test_cooldown_remaining_under_one_minute_rounds_up(self):
        user = UserFactory()
        favorite_new_cafe(user)
        request_favorite_map(user, now=tpe(2026, 10, 27, 10))

        favorite_new_cafe(user)
        result = request_favorite_map(user, now=tpe(2026, 10, 27, 10, 29, 30))

        assert result.status == 'cooldown'
        assert result.wait_minutes == 1

    def test_cooldown_ends_exactly_at_thirty_minutes(self):
        user = UserFactory()
        favorite_new_cafe(user)
        request_favorite_map(user, now=tpe(2026, 10, 27, 10))

        favorite_new_cafe(user)
        result = request_favorite_map(user, now=tpe(2026, 10, 27, 10, 30))

        assert result.status == 'generated'
        assert cafe_count(result) == 2

    def test_cooldown_does_not_apply_when_unchanged(self):
        user = UserFactory()
        favorite_new_cafe(user)
        request_favorite_map(user, now=tpe(2026, 10, 27, 10))

        result = request_favorite_map(user, now=tpe(2026, 10, 27, 10, 5))

        assert result.status == 'unchanged'
        assert result.wait_minutes is None

    def test_daily_limit_after_five_generations(self):
        user = UserFactory()
        start = tpe(2026, 10, 27, 9)
        for i in range(5):
            favorite_new_cafe(user)
            request_favorite_map(user, now=start + timedelta(minutes=30 * i))

        favorite_new_cafe(user)
        result = request_favorite_map(user, now=start + timedelta(minutes=150))

        assert result.status == 'daily_limit'
        assert result.url is not None
        assert cafe_count(result) == 5

    def test_daily_limit_takes_precedence_over_cooldown(self):
        """已用完 5 次時直接告知用完，不要先叫使用者等冷卻"""
        user = UserFactory()
        start = tpe(2026, 10, 27, 9)
        for i in range(5):
            favorite_new_cafe(user)
            request_favorite_map(user, now=start + timedelta(minutes=30 * i))  # 最後一次 11:00

        favorite_new_cafe(user)
        result = request_favorite_map(user, now=tpe(2026, 10, 27, 11, 10))

        assert result.status == 'daily_limit'
        assert result.wait_minutes is None

    def test_daily_count_resets_at_taipei_midnight(self):
        user = UserFactory()
        start = tpe(2026, 10, 27, 21, 20)
        for i in range(5):
            favorite_new_cafe(user)
            request_favorite_map(user, now=start + timedelta(minutes=30 * i))  # 最後一次 23:20
        favorite_new_cafe(user)
        assert request_favorite_map(user, now=tpe(2026, 10, 27, 23, 50)).status == 'daily_limit'

        assert request_favorite_map(user, now=tpe(2026, 10, 28, 0, 30)).status == 'generated'

        # 隔日從 1 開始計，還能再生成 4 次
        next_day = tpe(2026, 10, 28, 1, 0)
        for i in range(4):
            favorite_new_cafe(user)
            assert request_favorite_map(user, now=next_day + timedelta(minutes=30 * i)).status == 'generated'
        favorite_new_cafe(user)
        assert request_favorite_map(user, now=next_day + timedelta(minutes=120)).status == 'daily_limit'

    def test_day_boundary_uses_taipei_not_utc(self):
        """台北 07:00 為 UTC 前一日 23:00；以 UTC 計算會誤判為同一天而達上限"""
        user = UserFactory()
        start = tpe(2026, 10, 27, 10)
        for i in range(5):
            favorite_new_cafe(user)
            request_favorite_map(user, now=start + timedelta(minutes=30 * i))

        favorite_new_cafe(user)
        now = tpe(2026, 10, 28, 7).astimezone(ZoneInfo('UTC'))
        result = request_favorite_map(user, now=now)

        assert result.status == 'generated'


@pytest.mark.django_db
class TestGenerationFailure:
    """生成失敗不留半成品"""

    def test_failure_keeps_previous_version(self, caplog):
        user = UserFactory()
        favorite_new_cafe(user)
        first = request_favorite_map(user, now=tpe(2026, 10, 27, 10))
        before = get_map_snapshot(token_of(first.url))

        favorite_new_cafe(user)
        with patch('cafe.services.favorite_map.build_snapshot', side_effect=RuntimeError('boom')), \
                caplog.at_level(logging.ERROR):
            result = request_favorite_map(user, now=tpe(2026, 10, 27, 11))

        assert result.status == 'error'
        assert get_map_snapshot(token_of(first.url)) == before
        assert any(r.levelno >= logging.ERROR and r.exc_info for r in caplog.records)

    def test_failure_does_not_consume_cooldown_or_daily_count(self):
        user = UserFactory()
        start = tpe(2026, 10, 27, 9)
        for i in range(4):
            favorite_new_cafe(user)
            request_favorite_map(user, now=start + timedelta(minutes=30 * i))  # 已生成 4 次，最後 10:30

        favorite_new_cafe(user)
        with patch('cafe.services.favorite_map.build_snapshot', side_effect=RuntimeError('boom')):
            assert request_favorite_map(user, now=tpe(2026, 10, 27, 11)).status == 'error'

        # 失敗沒有重設冷卻、沒有計次：同一時間重試即可生成第 5 次
        assert request_favorite_map(user, now=tpe(2026, 10, 27, 11)).status == 'generated'

    def test_failure_on_first_creation_creates_nothing(self):
        user = UserFactory()
        favorite_new_cafe(user)

        with patch('cafe.services.favorite_map.build_snapshot', side_effect=RuntimeError('boom')):
            result = request_favorite_map(user, now=tpe(2026, 10, 27, 10))

        assert result.status == 'error'
        assert request_favorite_map(user, now=tpe(2026, 10, 27, 10)).status == 'created'


@pytest.mark.django_db
class TestConcurrentRequests:
    """並發生成防護：在生成過程中插入另一個請求，模擬同時送出"""

    @staticmethod
    def race_with(user, now):
        """回傳會在第一次組 snapshot 時先跑完另一個請求的 build_snapshot 替身"""
        real_build = favorite_map.build_snapshot
        state = {'inner': None}

        def build_with_race(*args, **kwargs):
            if state['inner'] is None:
                state['inner'] = 'running'
                state['inner'] = request_favorite_map(user, now=now)
            return real_build(*args, **kwargs)

        return build_with_race, state

    def test_concurrent_regeneration_generates_once(self):
        user = UserFactory()
        start = tpe(2026, 10, 27, 9)
        for i in range(3):
            favorite_new_cafe(user)
            request_favorite_map(user, now=start + timedelta(minutes=30 * i))  # 已生成 3 次，最後 10:00

        favorite_new_cafe(user)
        now = tpe(2026, 10, 27, 10, 30)
        build, state = self.race_with(user, now)
        with patch('cafe.services.favorite_map.build_snapshot', side_effect=build):
            outer = request_favorite_map(user, now=now)

        inner = state['inner']
        assert inner.status == 'generated'
        assert outer.status == 'unchanged'
        assert outer.url == inner.url

        # 兩個請求只計 1 次（共 4 次），所以冷卻後還能生成第 5 次
        favorite_new_cafe(user)
        assert request_favorite_map(user, now=tpe(2026, 10, 27, 11)).status == 'generated'
        favorite_new_cafe(user)
        assert request_favorite_map(user, now=tpe(2026, 10, 27, 11, 30)).status == 'daily_limit'

    def test_losing_race_twice_does_not_report_unchanged(self):
        """連續兩次被搶先寫入且收藏仍與地圖不同時，不可回報「未變動」"""
        user = UserFactory()
        favorite_new_cafe(user)
        request_favorite_map(user, now=tpe(2026, 10, 27, 8))

        real_build = favorite_map.build_snapshot
        competitor_times = iter([tpe(2026, 10, 27, 9), tpe(2026, 10, 27, 9, 30)])

        def build_with_two_races(*args, **kwargs):
            competitor_now = next(competitor_times, None)
            if competitor_now is not None:
                # 另一個請求以較早的時間先完成寫入，之後使用者又加了一間，地圖仍未反映最新收藏
                with patch('cafe.services.favorite_map.build_snapshot', side_effect=real_build):
                    request_favorite_map(user, now=competitor_now)
                favorite_new_cafe(user)
            return real_build(*args, **kwargs)

        favorite_new_cafe(user)
        with patch('cafe.services.favorite_map.build_snapshot', side_effect=build_with_two_races):
            result = request_favorite_map(user, now=tpe(2026, 10, 27, 12))

        assert result.status != 'unchanged'

    def test_concurrent_first_creation_creates_one_map(self):
        user = UserFactory()
        favorite_new_cafe(user)
        now = tpe(2026, 10, 27, 10)

        build, state = self.race_with(user, now)
        with patch('cafe.services.favorite_map.build_snapshot', side_effect=build):
            outer = request_favorite_map(user, now=now)

        inner = state['inner']
        assert inner.status == 'created'
        assert outer.status == 'unchanged'
        assert outer.url == inner.url
        assert request_favorite_map(user, now=now).url == inner.url


@pytest.mark.django_db
class TestBuildSnapshot:
    """snapshot 內容"""

    def test_full_cafe_fields(self):
        user = UserFactory()
        cafe = CafeFactory(
            place_id='ChIJ_full',
            name='好咖啡',
            address='台北市大安區復興南路一段 1 號',
            lat=Decimal('25.041234'),
            lng=Decimal('121.543210'),
            rating=Decimal('4.6'),
            user_ratings_total=321,
            phone='02 2345 6789',
            google_maps='https://maps.google.com/?cid=1',
            website='https://good.coffee',
            photo_s3_url='https://cdn.example.com/p.jpg',
            ai_summary='安靜、插座多',
            has_socket='yes',
            limited_time='no',
            pet_friendly=None,
            has_pet='maybe',
        )
        favorite = FavoriteFactory(user=user, cafe=cafe, note='拿鐵好喝')
        favorite.created_at = tpe(2026, 10, 20, 16)
        favorite.save(update_fields=['created_at'])

        snapshot = build_snapshot(user, now=tpe(2026, 10, 27, 10))

        assert snapshot['version'] == 1
        assert snapshot['generated_at'] == '2026-10-27T10:00:00+08:00'
        assert snapshot['cafes'] == [{
            'place_id': 'ChIJ_full',
            'name': '好咖啡',
            'address': '台北市大安區復興南路一段 1 號',
            'lat': 25.041234,
            'lng': 121.54321,
            'rating': 4.6,
            'user_ratings_total': 321,
            'phone': '02 2345 6789',
            'tel_uri': 'tel:0223456789',
            'google_maps': 'https://maps.google.com/?cid=1',
            'website': 'https://good.coffee',
            'photo_url': 'https://cdn.example.com/p.jpg',
            'ai_summary': '安靜、插座多',
            'attributes': {
                'has_socket': 'yes',
                'limited_time': 'no',
                'pet_friendly': None,
                'has_pet': 'maybe',
            },
            'note': '拿鐵好喝',
            'favorited_at': '2026-10-20T16:00:00+08:00',
        }]

    def test_generated_at_from_utc_now_is_taipei(self):
        user = UserFactory()

        snapshot = build_snapshot(user, now=datetime(2026, 10, 27, 2, tzinfo=ZoneInfo('UTC')))

        assert snapshot['generated_at'] == '2026-10-27T10:00:00+08:00'

    @pytest.mark.parametrize('lat, lng', [(None, Decimal('121.5')), (Decimal('25.0'), None), (None, None)])
    def test_cafe_without_coordinates_excluded(self, lat, lng):
        user = UserFactory()
        FavoriteFactory(user=user, cafe=CafeFactory(lat=lat, lng=lng))
        FavoriteFactory(user=user, cafe=CafeFactory(place_id='with_coords'))

        cafes = build_snapshot(user, now=tpe(2026, 10, 27, 10))['cafes']

        assert [c['place_id'] for c in cafes] == ['with_coords']

    def test_missing_values_are_null(self):
        user = UserFactory()
        cafe = CafeFactory(
            rating=None, phone=None, google_maps=None, website='', photo_s3_url='',
            ai_summary=None, has_socket=None, limited_time='', pet_friendly=None, has_pet=None,
        )
        FavoriteFactory(user=user, cafe=cafe, note='')

        item = build_snapshot(user, now=tpe(2026, 10, 27, 10))['cafes'][0]

        for key in ['rating', 'phone', 'tel_uri', 'google_maps', 'website', 'photo_url', 'ai_summary', 'note']:
            assert item[key] is None, key
        assert item['attributes'] == {
            'has_socket': None, 'limited_time': None, 'pet_friendly': None, 'has_pet': None,
        }

    @pytest.mark.parametrize('phone', ['無提供', '未提供電話', '---'])
    def test_placeholder_phone_is_null(self, phone):
        user = UserFactory()
        FavoriteFactory(user=user, cafe=CafeFactory(phone=phone))

        item = build_snapshot(user, now=tpe(2026, 10, 27, 10))['cafes'][0]

        assert item['phone'] is None
        assert item['tel_uri'] is None

    @pytest.mark.parametrize('note', [None, '', '   '])
    def test_blank_note_is_null(self, note):
        user = UserFactory()
        FavoriteFactory(user=user, cafe=CafeFactory(), note=note)

        assert build_snapshot(user, now=tpe(2026, 10, 27, 10))['cafes'][0]['note'] is None

    def test_ordered_by_favorited_newest_first(self):
        user = UserFactory()
        for place_id, day in [('old', 1), ('newest', 20), ('middle', 10)]:
            favorite = FavoriteFactory(user=user, cafe=CafeFactory(place_id=place_id))
            favorite.created_at = tpe(2026, 10, day, 12)
            favorite.save(update_fields=['created_at'])

        cafes = build_snapshot(user, now=tpe(2026, 10, 27, 10))['cafes']

        assert [c['place_id'] for c in cafes] == ['newest', 'middle', 'old']

    def test_only_own_favorites(self):
        user = UserFactory()
        FavoriteFactory(user=user, cafe=CafeFactory(place_id='mine'))
        FavoriteFactory(cafe=CafeFactory(place_id='others'))

        cafes = build_snapshot(user, now=tpe(2026, 10, 27, 10))['cafes']

        assert [c['place_id'] for c in cafes] == ['mine']

    def test_no_user_identity_in_snapshot(self):
        user = UserFactory(line_user_id='U' + 'f' * 32, display_name='小明咖啡控')
        FavoriteFactory(user=user, cafe=CafeFactory())

        dumped = json.dumps(build_snapshot(user, now=tpe(2026, 10, 27, 10)), ensure_ascii=False)

        assert user.line_user_id not in dumped
        assert '小明咖啡控' not in dumped

    def test_empty_favorites(self):
        snapshot = build_snapshot(UserFactory(), now=tpe(2026, 10, 27, 10))

        assert snapshot['cafes'] == []
