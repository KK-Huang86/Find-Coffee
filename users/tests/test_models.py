import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from users.models import User, Friendship
from users.tests.factories import UserFactory


@pytest.mark.django_db
class TestUserModel:
    """測試 User Model"""

    def test_create_user_auto_generate_member_code(self):
        """建立 User 時自動生成 member_code"""
        user = User.objects.create(line_user_id='U12345678901234567890123456789012')

        assert user.member_code is not None
        assert len(user.member_code) == 6
        assert user.member_code.isalnum()

    def test_create_user_with_existing_member_code(self):
        """提供 member_code 時不重新生成"""
        user = User.objects.create(
            line_user_id='U12345678901234567890123456789012',
            member_code='ABC123'
        )

        assert user.member_code == 'ABC123'

    def test_member_code_uniqueness(self):
        """member_code 必須唯一"""
        UserFactory(member_code='ABC123')

        with pytest.raises(IntegrityError):
            UserFactory(member_code='ABC123')

    def test_line_user_id_uniqueness(self):
        """line_user_id 必須唯一"""
        UserFactory(line_user_id='U12345678901234567890123456789012')

        with pytest.raises(IntegrityError):
            UserFactory(line_user_id='U12345678901234567890123456789012')

    def test_user_default_values(self):
        """測試 User 預設值"""
        user = UserFactory()

        assert user.member_type == User.FREE
        assert user.status == User.ACTIVE
        assert user.created_at is not None
        assert user.updated_at is not None

    def test_user_str_representation(self):
        """測試 User __str__ 方法"""
        user = UserFactory(line_user_id='U12345678901234567890123456789012')

        assert str(user) == 'U12345678901234567890123456789012'

    def test_member_code_auto_generated_uniqueness(self):
        """自動生成的 member_code 具有唯一性"""
        users = [UserFactory() for _ in range(10)]
        member_codes = [user.member_code for user in users]

        # 驗證所有 member_code 都不同
        assert len(member_codes) == len(set(member_codes))

    def test_member_code_format(self):
        """member_code 格式正確（6 位英數字）"""
        user = UserFactory()

        assert len(user.member_code) == 6
        assert user.member_code.isalnum()
        assert user.member_code.isupper() or user.member_code.isdigit()


@pytest.mark.django_db
class TestFriendshipModel:
    """測試 Friendship Model"""

    def test_create_friendship(self):
        """成功建立好友關係"""
        user1 = UserFactory()
        user2 = UserFactory()

        friendship = Friendship.objects.create(user=user1, friend=user2)

        assert friendship.user == user1
        assert friendship.friend == user2
        assert friendship.created_at is not None

    def test_prevent_self_friendship_in_clean(self):
        """clean() 方法阻止自己加自己為好友"""
        user = UserFactory()

        friendship = Friendship(user=user, friend=user)

        with pytest.raises(ValidationError, match='使用者不能加自己為好友'):
            friendship.clean()

    def test_prevent_self_friendship_in_save(self):
        """save() 方法自動呼叫 clean()，阻止自己加自己為好友"""
        user = UserFactory()

        with pytest.raises(ValidationError, match='使用者不能加自己為好友'):
            Friendship.objects.create(user=user, friend=user)

    def test_friendship_unique_together(self):
        """同一對使用者只能建立一次好友關係"""
        user1 = UserFactory()
        user2 = UserFactory()

        Friendship.objects.create(user=user1, friend=user2)

        with pytest.raises(IntegrityError):
            Friendship.objects.create(user=user1, friend=user2)

    def test_friendship_bidirectional_allowed(self):
        """允許雙向好友關係（user1 -> user2 和 user2 -> user1）"""
        user1 = UserFactory()
        user2 = UserFactory()

        friendship1 = Friendship.objects.create(user=user1, friend=user2)
        friendship2 = Friendship.objects.create(user=user2, friend=user1)

        assert friendship1.user == user1
        assert friendship1.friend == user2
        assert friendship2.user == user2
        assert friendship2.friend == user1

    def test_friendship_related_names(self):
        """測試 related_name 查詢"""
        user1 = UserFactory()
        user2 = UserFactory()
        user3 = UserFactory()

        Friendship.objects.create(user=user1, friend=user2)
        Friendship.objects.create(user=user1, friend=user3)

        # user1 的好友列表
        assert user1.friendships.count() == 2

        # user2 被誰加為好友
        assert user2.friend_of.count() == 1
