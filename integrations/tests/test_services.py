import pytest

from integrations.models import ApiUsageRecord
from integrations.services import ApiUsageService
from users.models import User


@pytest.mark.django_db
class TestGetSystemAiUserId:
    """測試 ApiUsageService.get_system_ai_user_id"""

    def test_creates_system_user_on_first_call(self):
        """首次呼叫時建立固定 line_user_id 的系統 User"""
        user_id = ApiUsageService.get_system_ai_user_id()

        user = User.objects.get(id=user_id)
        assert user.line_user_id == ApiUsageService.SYSTEM_AI_USER_LINE_ID

    def test_returns_same_id_on_repeated_calls(self):
        """重複呼叫回傳同一個 id，不建立第二筆系統 User（冪等性）"""
        first_id = ApiUsageService.get_system_ai_user_id()
        second_id = ApiUsageService.get_system_ai_user_id()

        assert first_id == second_id
        assert User.objects.filter(line_user_id=ApiUsageService.SYSTEM_AI_USER_LINE_ID).count() == 1

    def test_system_user_quota_independent_from_real_user(self):
        """系統帳號的額度計數與真人使用者的月額度完全分開"""
        from cafe.tests.factories import UserFactory

        real_user = UserFactory()
        system_user_id = ApiUsageService.get_system_ai_user_id()

        ApiUsageService.try_increment_ai_calls(system_user_id)

        real_user_record, _ = ApiUsageRecord.objects.get_or_create(
            user_id=real_user.id, year_month=ApiUsageService._get_year_month()
        )
        assert real_user_record.ai_calls == 0


@pytest.mark.django_db
class TestSystemAiQuotaUsingExistingInterface:
    """驗證系統帳號 id 搭配既有 try_increment_ai_calls / revert_ai_call 的行為（不新增第二套額度系統）"""

    def test_quota_available_can_be_consumed(self):
        """額度充足時可成功佔用"""
        system_user_id = ApiUsageService.get_system_ai_user_id()

        ok = ApiUsageService.try_increment_ai_calls(system_user_id)

        assert ok is True
        record = ApiUsageRecord.objects.get(user_id=system_user_id, year_month=ApiUsageService._get_year_month())
        assert record.ai_calls == 1

    def test_quota_exhausted_returns_false(self):
        """額度用盡時回傳 False，且不再累加"""
        system_user_id = ApiUsageService.get_system_ai_user_id()
        year_month = ApiUsageService._get_year_month()
        ApiUsageRecord.objects.create(
            user_id=system_user_id, year_month=year_month, ai_calls=1, monthly_ai_limit=1,
        )

        ok = ApiUsageService.try_increment_ai_calls(system_user_id)

        assert ok is False
        record = ApiUsageRecord.objects.get(user_id=system_user_id, year_month=year_month)
        assert record.ai_calls == 1

    def test_revert_after_failure_keeps_net_zero(self):
        """呼叫失敗後 revert 額度，淨消耗歸零"""
        system_user_id = ApiUsageService.get_system_ai_user_id()

        ApiUsageService.try_increment_ai_calls(system_user_id)
        ApiUsageService.revert_ai_call(system_user_id)

        record = ApiUsageRecord.objects.get(
            user_id=system_user_id, year_month=ApiUsageService._get_year_month()
        )
        assert record.ai_calls == 0


@pytest.mark.django_db
class TestRecordAiCall:
    """測試 ApiUsageService.record_ai_call：只記錄用量、不受上限阻擋（背景 AI 摘要使用）"""

    def _record(self, user_id):
        return ApiUsageRecord.objects.get(user_id=user_id, year_month=ApiUsageService._get_year_month())

    def test_creates_record_and_counts_one(self):
        """當月尚無紀錄時建立紀錄並記為 1"""
        user_id = ApiUsageService.get_system_ai_user_id()

        ApiUsageService.record_ai_call(user_id)

        assert self._record(user_id).ai_calls == 1

    def test_counts_beyond_monthly_limit(self):
        """已達或超過月上限時仍照常累加，不阻擋"""
        user_id = ApiUsageService.get_system_ai_user_id()
        ApiUsageRecord.objects.create(
            user_id=user_id, year_month=ApiUsageService._get_year_month(), ai_calls=50, monthly_ai_limit=50,
        )

        ApiUsageService.record_ai_call(user_id)
        ApiUsageService.record_ai_call(user_id)

        assert self._record(user_id).ai_calls == 52

    def test_counts_when_can_use_ai_false(self):
        """can_use_ai 為 False 時仍記錄，且不改動 can_use_ai"""
        user_id = ApiUsageService.get_system_ai_user_id()
        ApiUsageRecord.objects.create(
            user_id=user_id, year_month=ApiUsageService._get_year_month(), ai_calls=3, can_use_ai=False,
        )

        ApiUsageService.record_ai_call(user_id)

        record = self._record(user_id)
        assert record.ai_calls == 4
        assert record.can_use_ai is False

    def test_does_not_touch_other_counters(self):
        """只累加 ai_calls，不影響 Google API 相關計數"""
        user_id = ApiUsageService.get_system_ai_user_id()

        ApiUsageService.record_ai_call(user_id)

        record = self._record(user_id)
        assert record.total_api_calls == 0
        assert record.search_calls == 0
        assert record.detail_calls == 0

    def test_does_not_affect_other_users(self):
        """只記在指定帳號，不影響真人使用者"""
        system_user_id = ApiUsageService.get_system_ai_user_id()
        real_user = User.objects.create(line_user_id='U_real_user')

        ApiUsageService.record_ai_call(system_user_id)

        assert not ApiUsageRecord.objects.filter(user=real_user).exists()
