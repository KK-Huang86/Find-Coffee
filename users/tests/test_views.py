import pytest
from decimal import Decimal

from users.views import FavoritesManager
from users.tests.factories import UserFactory
from cafe.tests.factories import CafeFactory
from cafe.models import Cafe, Favorite


@pytest.mark.django_db
class TestFavoritesManagerAddFavorite:
    """測試 FavoritesManager.add_favorite"""

    def test_add_favorite_cafe_exists(self, mocker):
        """成功新增收藏（Cafe 已存在）"""
        user = UserFactory()
        cafe = CafeFactory(place_id='ChIJ123', name='測試咖啡店')

        # Mock parse_opening_hours
        mock_parse = mocker.patch('users.views.parse_opening_hours')
        mock_parse.return_value = {'星期一': '09:00 - 18:00'}

        info = {
            'place_id': 'ChIJ123',
            'name': '測試咖啡店',
            'address': '台北市信義區',
            'lat': 25.033,
            'lng': 121.564,
        }

        success, message = FavoritesManager.add_favorite(user, info)

        assert success is True
        assert '已收藏「測試咖啡店」' in message
        assert Favorite.objects.filter(user=user, cafe=cafe).exists()

        # 驗證 favorite_count 增加
        cafe.refresh_from_db()
        assert cafe.favorite_count == 1

    def test_add_favorite_create_new_cafe(self, mocker):
        """成功新增收藏（Cafe 不存在，建立新 Cafe）"""
        user = UserFactory()

        mock_parse = mocker.patch('users.views.parse_opening_hours')
        mock_parse.return_value = {'星期一': '09:00 - 18:00'}

        info = {
            'place_id': 'ChIJ999',
            'name': '新咖啡店',
            'address': '台北市大安區',
            'phone': '02-1234-5678',
            'lat': 25.033,
            'lng': 121.564,
            'rating': 4.5,
            'user_ratings_total': 100,
            'google_maps': 'https://maps.google.com/xxx',
            'website': 'https://example.com',
            'opening_hours': ['星期一: 09:00 - 18:00'],
        }

        success, message = FavoritesManager.add_favorite(user, info)

        assert success is True
        assert '已收藏「新咖啡店」' in message

        # 驗證 Cafe 被建立
        cafe = Cafe.objects.get(place_id='ChIJ999')
        assert cafe.name == '新咖啡店'
        assert cafe.address == '台北市大安區'
        assert cafe.phone == '02-1234-5678'
        assert cafe.lat == Decimal('25.033')
        assert cafe.lng == Decimal('121.564')
        assert cafe.rating == Decimal('4.5')
        assert cafe.user_ratings_total == 100
        assert cafe.google_maps == 'https://maps.google.com/xxx'
        assert cafe.website == 'https://example.com'
        assert cafe.opening_hours == {'星期一': '09:00 - 18:00'}
        assert cafe.favorite_count == 1

        # 驗證 Favorite 被建立
        assert Favorite.objects.filter(user=user, cafe=cafe).exists()

    def test_add_favorite_already_exists(self, mocker):
        """已經收藏過的情況"""
        user = UserFactory()
        cafe = CafeFactory(place_id='ChIJ123', name='測試咖啡店')
        Favorite.objects.create(user=user, cafe=cafe)

        mock_parse = mocker.patch('users.views.parse_opening_hours')
        mock_parse.return_value = {}

        info = {
            'place_id': 'ChIJ123',
            'name': '測試咖啡店',
        }

        success, message = FavoritesManager.add_favorite(user, info)

        assert success is False
        assert '已在您的收藏清單中' in message

        # favorite_count 不應增加
        cafe.refresh_from_db()
        assert cafe.favorite_count == 0

    def test_add_favorite_missing_place_id(self):
        """資訊不完整（缺少 place_id）"""
        user = UserFactory()

        info = {'name': '測試咖啡店'}

        success, message = FavoritesManager.add_favorite(user, info)

        assert success is False
        assert message == '咖啡店資訊不完整'

    def test_add_favorite_missing_name(self):
        """資訊不完整（缺少 name）"""
        user = UserFactory()

        info = {'place_id': 'ChIJ123'}

        success, message = FavoritesManager.add_favorite(user, info)

        assert success is False
        assert message == '咖啡店資訊不完整'

    def test_add_favorite_empty_opening_hours(self, mocker):
        """opening_hours 為空時正確處理"""
        user = UserFactory()

        mock_parse = mocker.patch('users.views.parse_opening_hours')
        mock_parse.return_value = {}

        info = {
            'place_id': 'ChIJ999',
            'name': '新咖啡店',
            'opening_hours': [],
        }

        success, message = FavoritesManager.add_favorite(user, info)

        assert success is True
        mock_parse.assert_called_once_with([])

    def test_add_favorite_handles_exception(self, mocker):
        """處理一般異常"""
        user = UserFactory()

        # Mock parse_opening_hours 正常運作
        mock_parse = mocker.patch('users.views.parse_opening_hours')
        mock_parse.return_value = {}

        # Mock Cafe.objects.get_or_create 拋出異常
        mocker.patch.object(Cafe.objects, 'get_or_create', side_effect=Exception('測試異常'))

        info = {
            'place_id': 'ChIJ123',
            'name': '測試咖啡店',
        }

        success, message = FavoritesManager.add_favorite(user, info)

        assert success is False
        assert message == '系統錯誤，請稍後再試'

    def test_add_favorite_increment_called(self, mocker):
        """驗證 increment_favorite_count 被呼叫"""
        user = UserFactory()
        cafe = CafeFactory(place_id='ChIJ123', name='測試咖啡店')

        mock_parse = mocker.patch('users.views.parse_opening_hours')
        mock_parse.return_value = {}

        # Spy on increment_favorite_count
        mock_increment = mocker.spy(Cafe, 'increment_favorite_count')

        info = {
            'place_id': 'ChIJ123',
            'name': '測試咖啡店',
        }

        FavoritesManager.add_favorite(user, info)

        assert mock_increment.call_count == 1


@pytest.mark.django_db
class TestFavoritesManagerRemoveFavorite:
    """測試 FavoritesManager.remove_favorite"""

    def test_remove_favorite_success(self, mocker):
        """成功移除收藏"""
        user = UserFactory()
        cafe = CafeFactory(place_id='ChIJ123', name='測試咖啡店', favorite_count=1)
        Favorite.objects.create(user=user, cafe=cafe)

        info = {
            'place_id': 'ChIJ123',
            'name': '測試咖啡店',
        }

        success, message = FavoritesManager.remove_favorite(user, info)

        assert success is True
        assert '已取消收藏「測試咖啡店」' in message
        assert not Favorite.objects.filter(user=user, cafe=cafe).exists()

        # 驗證 favorite_count 減少
        cafe.refresh_from_db()
        assert cafe.favorite_count == 0

    def test_remove_favorite_cafe_not_found(self):
        """Cafe 不存在"""
        user = UserFactory()

        info = {
            'place_id': 'ChIJ999',
            'name': '不存在的咖啡店',
        }

        success, message = FavoritesManager.remove_favorite(user, info)

        assert success is False
        assert message == '找不到該咖啡店'

    def test_remove_favorite_not_in_favorites(self):
        """Favorite 不存在（未曾收藏）"""
        user = UserFactory()
        cafe = CafeFactory(place_id='ChIJ123', name='測試咖啡店')

        info = {
            'place_id': 'ChIJ123',
            'name': '測試咖啡店',
        }

        success, message = FavoritesManager.remove_favorite(user, info)

        assert success is False
        assert '不在您的收藏清單中' in message

    def test_remove_favorite_missing_place_id(self):
        """資訊不完整（缺少 place_id）"""
        user = UserFactory()

        info = {'name': '測試咖啡店'}

        success, message = FavoritesManager.remove_favorite(user, info)

        assert success is False
        assert message == '咖啡店資訊不完整'

    def test_remove_favorite_missing_name(self):
        """資訊不完整（缺少 name）"""
        user = UserFactory()

        info = {'place_id': 'ChIJ123'}

        success, message = FavoritesManager.remove_favorite(user, info)

        assert success is False
        assert message == '咖啡店資訊不完整'

    def test_remove_favorite_handles_exception(self, mocker):
        """處理一般異常"""
        user = UserFactory()

        # Mock Cafe.objects.filter 拋出異常
        mocker.patch.object(Cafe.objects, 'filter', side_effect=Exception('測試異常'))

        info = {
            'place_id': 'ChIJ123',
            'name': '測試咖啡店',
        }

        success, message = FavoritesManager.remove_favorite(user, info)

        assert success is False
        assert message == '系統錯誤，請稍後再試'

    def test_remove_favorite_decrement_called(self, mocker):
        """驗證 decrement_favorite_count 被呼叫"""
        user = UserFactory()
        cafe = CafeFactory(place_id='ChIJ123', name='測試咖啡店', favorite_count=1)
        Favorite.objects.create(user=user, cafe=cafe)

        # Spy on decrement_favorite_count
        mock_decrement = mocker.spy(Cafe, 'decrement_favorite_count')

        info = {
            'place_id': 'ChIJ123',
            'name': '測試咖啡店',
        }

        FavoritesManager.remove_favorite(user, info)

        assert mock_decrement.call_count == 1
