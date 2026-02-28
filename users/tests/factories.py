import factory

from users.models import User, Friendship


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    line_user_id = factory.Sequence(lambda n: f'U{n:032d}')
    display_name = factory.Faker('name', locale='zh_TW')
    member_type = User.FREE
    status = User.ACTIVE


class FriendshipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Friendship

    user = factory.SubFactory(UserFactory)
    friend = factory.SubFactory(UserFactory)
