import factory
from decimal import Decimal

from cafe.models import Cafe


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
