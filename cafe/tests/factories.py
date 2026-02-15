import factory
from decimal import Decimal

from cafe.models import Cafe, Favorite, CafeAttributeVote, CafeNomadCache
from users.models import User


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    line_user_id = factory.Sequence(lambda n: f'U{n:032d}')
    display_name = factory.Faker('name', locale='zh_TW')
    member_code = factory.Sequence(lambda n: f'M{n:05d}')
    member_type = User.FREE
    status = User.ACTIVE


class CafeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Cafe

    place_id = factory.Sequence(lambda n: f'place_id_{n}')
    name = factory.Faker('company', locale='zh_TW')
    address = factory.Faker('address', locale='zh_TW')
    lat = factory.LazyFunction(lambda: Decimal('25.033964'))
    lng = factory.LazyFunction(lambda: Decimal('121.564468'))
    rating = factory.LazyFunction(lambda: Decimal('4.5'))
    user_ratings_total = 100
    photo_reference = ''
    photo_s3_url = ''


class FavoriteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Favorite

    user = factory.SubFactory(UserFactory)
    cafe = factory.SubFactory(CafeFactory)
    note = ''
    is_public = False


class CafeAttributeVoteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CafeAttributeVote

    cafe = factory.SubFactory(CafeFactory)
    user = factory.SubFactory(UserFactory)
    attribute = 'socket'
    value = 'yes'
    source = 'user'


class CafeNomadCacheFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CafeNomadCache

    cafenomad_id = factory.Sequence(lambda n: f'cafenomad_{n}')
    name = factory.Faker('company', locale='zh_TW')
    city = '台北市'
    address = factory.Faker('address', locale='zh_TW')
    lat = factory.LazyFunction(lambda: Decimal('25.033964'))
    lng = factory.LazyFunction(lambda: Decimal('121.564468'))
    socket = 'yes'
    limited_time = 'no'
