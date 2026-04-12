import pytest
from decimal import Decimal
from django.db import IntegrityError
from django.utils import timezone

from cafe.models import Cafe
from cafe.tests.factories import (
    CafeFactory,
    UserFactory,
    FavoriteFactory,
    CafeAttributeVoteFactory,
    CafeNomadCacheFactory,
)


# Cafe Model Tests


@pytest.mark.django_db
class TestCafeModel:

    def test_cafe_creation(self):
        """測試 Cafe 基本建立"""
        cafe = CafeFactory(
            name='測試咖啡店',
            address='台北市信義區',
            rating=Decimal('4.5'),
        )

        assert cafe.pk is not None
        assert cafe.name == '測試咖啡店'
        assert cafe.address == '台北市信義區'
        assert cafe.rating == Decimal('4.5')
        assert cafe.favorite_count == 0

    def test_cafe_str_method(self):
        """測試 __str__ 方法"""
        cafe = CafeFactory(name='星巴克信義店')
        assert str(cafe) == '星巴克信義店'

    def test_increment_favorite_count(self):
        """測試增加收藏數"""
        cafe = CafeFactory(favorite_count=0)

        cafe.increment_favorite_count()

        assert cafe.favorite_count == 1

    def test_increment_favorite_count_multiple_times(self):
        """測試多次增加收藏數"""
        cafe = CafeFactory(favorite_count=5)

        cafe.increment_favorite_count()
        cafe.increment_favorite_count()
        cafe.increment_favorite_count()

        assert cafe.favorite_count == 8

    def test_decrement_favorite_count(self):
        """測試減少收藏數"""
        cafe = CafeFactory(favorite_count=5)

        cafe.decrement_favorite_count()

        assert cafe.favorite_count == 4

    def test_decrement_favorite_count_not_below_zero(self):
        """測試收藏數不會低於 0"""
        cafe = CafeFactory(favorite_count=0)

        cafe.decrement_favorite_count()

        assert cafe.favorite_count == 0

    def test_decrement_favorite_count_from_one_to_zero(self):
        """測試從 1 減到 0"""
        cafe = CafeFactory(favorite_count=1)

        cafe.decrement_favorite_count()

        assert cafe.favorite_count == 0

    def test_to_dict(self):
        """測試 to_dict 方法"""
        cafe = CafeFactory(
            name='測試咖啡店',
            address='台北市信義區',
            phone='02-12345678',
            rating=Decimal('4.5'),
            user_ratings_total=100,
            place_id='test_place_id',
            google_maps='https://maps.google.com/test',
            website='https://test.com',
            lat=Decimal('25.033964'),
            lng=Decimal('121.564468'),
            opening_hours=['週一: 09:00-21:00'],
            limited_time='no',
            has_socket='yes',
            photo_reference='photo_ref_123',
            photo_s3_url='https://s3.amazonaws.com/test.jpg',
            last_refreshed=None,
        )

        result = cafe.to_dict()

        assert result['name'] == '測試咖啡店'
        assert result['address'] == '台北市信義區'
        assert result['phone'] == '02-12345678'
        assert result['rating'] == Decimal('4.5')
        assert result['user_ratings_total'] == 100
        assert result['place_id'] == 'test_place_id'
        assert result['google_maps'] == 'https://maps.google.com/test'
        assert result['website'] == 'https://test.com'
        assert result['lat'] == pytest.approx(25.033964)
        assert result['lng'] == pytest.approx(121.564468)
        assert result['opening_hours'] == ['週一: 09:00-21:00']
        assert result['limited_time'] == 'no'
        assert result['has_socket'] == 'yes'
        assert result['photo_reference'] == 'photo_ref_123'
        assert result['photo_s3_url'] == 'https://s3.amazonaws.com/test.jpg'
        assert result['last_refreshed'] is None

    def test_to_dict_with_last_refreshed(self):
        """測試 to_dict 有 last_refreshed 時的轉換"""
        refresh_time = timezone.now()
        cafe = CafeFactory(last_refreshed=refresh_time)

        result = cafe.to_dict()

        assert result['last_refreshed'] == refresh_time.isoformat()

    def test_get_popular_cafes(self):
        """測試取得熱門咖啡店"""
        # 先清空資料
        Cafe.objects.all().delete()

        # 建立多間咖啡店，收藏數不同
        cafe1 = CafeFactory(name='熱門店1', favorite_count=100)
        cafe2 = CafeFactory(name='熱門店2', favorite_count=50)
        cafe3 = CafeFactory(name='熱門店3', favorite_count=200)
        cafe4 = CafeFactory(name='普通店', favorite_count=10)

        popular = Cafe.get_popular_cafes()

        assert len(popular) == 4
        assert popular[0] == cafe3  # 最多收藏
        assert popular[1] == cafe1
        assert popular[2] == cafe2
        assert popular[3] == cafe4

    def test_get_popular_cafes_limit_10(self):
        """測試熱門咖啡店最多回傳 10 間"""
        # 先清空資料
        Cafe.objects.all().delete()

        # 建立 15 間咖啡店
        for i in range(15):
            CafeFactory(favorite_count=i)

        popular = Cafe.get_popular_cafes()

        assert len(popular) == 10

    def test_place_id_unique(self):
        """測試 place_id 唯一性"""
        CafeFactory(place_id='unique_id')

        with pytest.raises(IntegrityError):
            CafeFactory(place_id='unique_id')


# Favorite Model Tests

@pytest.mark.django_db
class TestFavoriteModel:
    """Favorite 模型測試"""

    def test_favorite_creation(self):
        """測試建立收藏"""
        user = UserFactory()
        cafe = CafeFactory()

        favorite = FavoriteFactory(user=user, cafe=cafe, note='好喝!')

        assert favorite.pk is not None
        assert favorite.user == user
        assert favorite.cafe == cafe
        assert favorite.note == '好喝!'
        assert favorite.is_public is False

    def test_favorite_unique_together(self):
        """測試同一使用者不能重複收藏同一間店"""
        user = UserFactory()
        cafe = CafeFactory()

        FavoriteFactory(user=user, cafe=cafe)

        with pytest.raises(IntegrityError):
            FavoriteFactory(user=user, cafe=cafe)

    def test_different_user_can_favorite_same_cafe(self):
        """測試不同使用者可以收藏同一間店"""
        cafe = CafeFactory()
        user1 = UserFactory()
        user2 = UserFactory()

        fav1 = FavoriteFactory(user=user1, cafe=cafe)
        fav2 = FavoriteFactory(user=user2, cafe=cafe)

        assert fav1.pk is not None
        assert fav2.pk is not None
        assert fav1.pk != fav2.pk

    def test_same_user_can_favorite_different_cafes(self):
        """測試同一使用者可以收藏不同店"""
        user = UserFactory()
        cafe1 = CafeFactory()
        cafe2 = CafeFactory()

        fav1 = FavoriteFactory(user=user, cafe=cafe1)
        fav2 = FavoriteFactory(user=user, cafe=cafe2)

        assert fav1.pk is not None
        assert fav2.pk is not None


# CafeAttributeVote Model Tests

@pytest.mark.django_db
class TestCafeAttributeVoteModel:
    """CafeAttributeVote 模型測試"""

    def test_vote_creation(self):
        """測試建立投票"""
        cafe = CafeFactory()
        user = UserFactory()

        vote = CafeAttributeVoteFactory(
            cafe=cafe,
            user=user,
            attribute='socket',
            value='yes',
            source='user',
        )

        assert vote.pk is not None
        assert vote.cafe == cafe
        assert vote.user == user
        assert vote.attribute == 'socket'
        assert vote.value == 'yes'
        assert vote.source == 'user'

    def test_vote_str_method(self):
        """測試 __str__ 方法"""
        cafe = CafeFactory(name='測試咖啡店')
        vote = CafeAttributeVoteFactory(
            cafe=cafe,
            attribute='socket',
            value='yes',
        )

        assert str(vote) == '測試咖啡店 - 插座: 是/有'

    def test_unique_user_vote_per_attribute(self):
        """測試同一使用者對同一店家的同一屬性只能投一次票"""
        cafe = CafeFactory()
        user = UserFactory()

        CafeAttributeVoteFactory(
            cafe=cafe,
            user=user,
            attribute='socket',
            value='yes',
        )

        with pytest.raises(IntegrityError):
            CafeAttributeVoteFactory(
                cafe=cafe,
                user=user,
                attribute='socket',
                value='no',
            )

    def test_same_user_can_vote_different_attributes(self):
        """測試同一使用者可以對不同屬性投票"""
        cafe = CafeFactory()
        user = UserFactory()

        vote1 = CafeAttributeVoteFactory(
            cafe=cafe,
            user=user,
            attribute='socket',
            value='yes',
        )
        vote2 = CafeAttributeVoteFactory(
            cafe=cafe,
            user=user,
            attribute='limited_time',
            value='no',
        )

        assert vote1.pk is not None
        assert vote2.pk is not None

    def test_different_users_can_vote_same_attribute(self):
        """測試不同使用者可以對同一屬性投票"""
        cafe = CafeFactory()
        user1 = UserFactory()
        user2 = UserFactory()

        vote1 = CafeAttributeVoteFactory(cafe=cafe, user=user1, attribute='socket')
        vote2 = CafeAttributeVoteFactory(cafe=cafe, user=user2, attribute='socket')

        assert vote1.pk is not None
        assert vote2.pk is not None

    def test_cafenomad_source_can_create_without_user(self):
        """測試 CafeNomad 來源可以不指定使用者"""
        cafe = CafeFactory()

        vote = CafeAttributeVoteFactory(
            cafe=cafe,
            user=None,
            attribute='socket',
            value='yes',
            source='cafenomad',
        )

        assert vote.pk is not None
        assert vote.user is None
        assert vote.source == 'cafenomad'


# CafeNomadCache Model Tests

@pytest.mark.django_db
class TestCafeNomadCacheModel:

    def test_cache_creation(self):
        """測試建立 CafeNomad 資料"""
        cache = CafeNomadCacheFactory(
            name='路易莎咖啡',
            city='台北市',
            address='信義區信義路五段',
            lat=Decimal('25.033964'),
            lng=Decimal('121.564468'),
            socket='yes',
            limited_time='no',
        )

        assert cache.pk is not None
        assert cache.name == '路易莎咖啡'
        assert cache.city == '台北市'
        assert cache.socket == 'yes'
        assert cache.limited_time == 'no'

    def test_cache_str_method(self):
        """測試 __str__ 方法"""
        cache = CafeNomadCacheFactory(name='星巴克', city='台北市')
        assert str(cache) == '星巴克 (台北市)'

    def test_cafenomad_id_unique(self):
        """測試 cafenomad_id 唯一性"""
        CafeNomadCacheFactory(cafenomad_id='unique_id')

        with pytest.raises(IntegrityError):
            CafeNomadCacheFactory(cafenomad_id='unique_id')

    def test_has_complete_attributes_true(self):
        """測試有完整屬性時回傳 True"""
        cache = CafeNomadCacheFactory(
            socket='yes',
            limited_time='no',
        )

        assert cache.has_complete_attributes is True

    def test_has_complete_attributes_false_missing_socket(self):
        """測試缺少 socket 時回傳 False"""
        cache = CafeNomadCacheFactory(
            socket=None,
            limited_time='no',
        )

        assert cache.has_complete_attributes is False

    def test_has_complete_attributes_false_missing_limited_time(self):
        """測試缺少 limited_time 時回傳 False"""
        cache = CafeNomadCacheFactory(
            socket='yes',
            limited_time=None,
        )

        assert cache.has_complete_attributes is False

    def test_has_complete_attributes_false_both_missing(self):
        """測試兩者都缺少時回傳 False"""
        cache = CafeNomadCacheFactory(
            socket=None,
            limited_time=None,
        )

        assert cache.has_complete_attributes is False

    def test_to_dict(self):
        """測試 to_dict 方法"""
        cache = CafeNomadCacheFactory(
            name='測試咖啡店',
            city='台北市',
            address='信義區信義路',
            lat=Decimal('25.033964'),
            lng=Decimal('121.564468'),
            socket='yes',
            limited_time='no',
        )

        result = cache.to_dict()

        assert result['name'] == '測試咖啡店'
        assert result['city'] == '台北市'
        assert result['address'] == '信義區信義路'
        assert result['lat'] == pytest.approx(25.033964)
        assert result['lng'] == pytest.approx(121.564468)
        assert result['socket'] == 'yes'
        assert result['limited_time'] == 'no'

    def test_optional_rating_fields(self):
        """測試評分欄位可為空"""
        cache = CafeNomadCacheFactory(
            wifi=4.5,
            seat=3.8,
            quiet=4.0,
            tasty=4.2,
            cheap=3.5,
            music=4.1,
        )

        assert cache.wifi == 4.5
        assert cache.seat == 3.8
        assert cache.quiet == 4.0
        assert cache.tasty == 4.2
        assert cache.cheap == 3.5
        assert cache.music == 4.1

    def test_optional_fields_can_be_null(self):
        """測試選填欄位可為 null"""
        cache = CafeNomadCacheFactory(
            wifi=None,
            seat=None,
            standing_desk=None,
            mrt='',
        )

        assert cache.wifi is None
        assert cache.seat is None
        assert cache.standing_desk is None
        assert cache.mrt == ''
