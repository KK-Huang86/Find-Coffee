import logging
from unittest.mock import patch

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

    def test_member_code_first_attempt_no_collision_does_not_retry(self):
        """member_code 首次產生即不衝突時，使用者建立成功、不觸發 retry"""
        with patch('users.models.random.choices', return_value=list('AAAAAA')) as mock_choices:
            user = User.objects.create(line_user_id='U_first_attempt_ok')

        assert user.member_code == 'AAAAAA'
        mock_choices.assert_called_once()

    def test_member_code_retries_after_collision(self):
        """member_code 首次產生與既有使用者衝突，重試後產生未衝突代號時仍建立成功"""
        UserFactory(member_code='AAAAAA')

        with patch('users.models.random.choices', side_effect=[list('AAAAAA'), list('BBBBBB')]):
            user = User.objects.create(line_user_id='U_retry_success')

        assert user.member_code == 'BBBBBB'

    def test_member_code_retry_succeeds_when_nested_in_outer_transaction(self):
        """
        關鍵：巢狀 transaction 情境的重試證明。

        @pytest.mark.django_db 本身即讓每個測試跑在 outer atomic transaction 中，
        天然滿足此情境，不需額外 mock transaction。呼叫 get_or_create（沿用實際生產
        呼叫路徑），若 retry loop 沒有各自用 savepoint 保護，第一次撞號後 transaction
        會被標記 aborted，第二次 super().save() 會拋非 IntegrityError 的例外，
        導致本測試失敗。
        """
        UserFactory(member_code='AAAAAA')

        with patch('users.models.random.choices', side_effect=[list('AAAAAA'), list('BBBBBB')]):
            user, created = User.objects.get_or_create(line_user_id='U_nested_tx_ok')

        assert created is True
        assert user.member_code == 'BBBBBB'

    def test_member_code_raises_after_max_retries_exhausted(self):
        """連續 10 次產生的 member_code 皆與既有使用者衝突時，最終拋出明確的 IntegrityError"""
        UserFactory(member_code='AAAAAA')

        with patch('users.models.random.choices', return_value=list('AAAAAA')):
            with pytest.raises(IntegrityError):
                User.objects.create(line_user_id='U_exhausted')

    def test_save_atomic_uses_router_resolved_alias(self):
        """
        save() 未顯式指定 using 時，atomic() 使用 router.db_for_write 解析出的連線別名。

        額外 patch django.db.models.Model.save，避免 super().save() 真的嘗試連線到
        測試環境不存在的 'some_alias'，確保測的是「using 有沒有正確傳給 atomic()」
        本身，而不是意外觸發 ConnectionDoesNotExist。
        """
        user = UserFactory.build(line_user_id='U_router_alias', member_code='')

        with patch('users.models.transaction.atomic') as mock_atomic, \
             patch('users.models.router.db_for_write', return_value='some_alias'), \
             patch('django.db.models.Model.save') as mock_model_save:
            user.save()

        mock_atomic.assert_called_once_with(using='some_alias')
        mock_model_save.assert_called_once()

    def test_save_atomic_uses_explicit_using_kwarg(self):
        """save(using=...) 顯式指定時，atomic() 使用該別名，優先於 router 解析結果"""
        user = UserFactory.build(line_user_id='U_explicit_alias', member_code='')

        with patch('users.models.transaction.atomic') as mock_atomic, \
             patch('users.models.router.db_for_write', return_value='some_alias'), \
             patch('django.db.models.Model.save') as mock_model_save:
            user.save(using='explicit_alias')

        mock_atomic.assert_called_once_with(using='explicit_alias')
        mock_model_save.assert_called_once()

    def test_member_code_collision_retry_logs_warning(self, caplog):
        """撞號後觸發重試時，記錄可追蹤的 WARNING 紀錄，內容包含 line_user_id"""
        UserFactory(member_code='AAAAAA')

        with caplog.at_level(logging.WARNING, logger='users.models'):
            with patch('users.models.random.choices', side_effect=[list('AAAAAA'), list('BBBBBB')]):
                User.objects.create(line_user_id='U_logs_warning')

        warning_records = [r for r in caplog.records if r.levelname == 'WARNING']
        assert len(warning_records) == 1
        assert 'U_logs_warning' in caplog.text

    def test_member_code_exhausted_retries_logs_error(self, caplog):
        """重試上限用盡時，記錄可追蹤的 ERROR 紀錄，內容包含 line_user_id"""
        UserFactory(member_code='AAAAAA')

        with caplog.at_level(logging.WARNING, logger='users.models'):
            with patch('users.models.random.choices', return_value=list('AAAAAA')):
                with pytest.raises(IntegrityError):
                    User.objects.create(line_user_id='U_logs_error')

        error_records = [r for r in caplog.records if r.levelname == 'ERROR']
        assert len(error_records) == 1
        assert 'U_logs_error' in caplog.text

    def test_member_code_first_attempt_success_logs_nothing(self, caplog):
        """首次即成功時，不產生撞號相關 WARNING/ERROR log，避免正常路徑製造雜訊"""
        with caplog.at_level(logging.WARNING, logger='users.models'):
            with patch('users.models.random.choices', return_value=list('AAAAAA')):
                User.objects.create(line_user_id='U_no_noise')

        noisy_records = [r for r in caplog.records if r.levelname in ('WARNING', 'ERROR')]
        assert noisy_records == []


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
