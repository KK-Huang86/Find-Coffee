from io import StringIO

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError

from cafe.tests.factories import CafeFactory
from integrations.models import ApiUsageRecord
from integrations.services import ApiUsageService
from utils.utils import LockService

COMMAND = 'backfill_ai_summary'
SLEEP_PATH = 'cafe.management.commands.backfill_ai_summary.time.sleep'


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def mock_sleep(mocker):
    return mocker.patch(SLEEP_PATH)


def _set_system_quota(limit, used=0, can_use_ai=True):
    user_id = ApiUsageService.get_system_ai_user_id()
    record, _ = ApiUsageRecord.objects.get_or_create(
        user_id=user_id, year_month=ApiUsageService._get_year_month()
    )
    ApiUsageRecord.objects.filter(pk=record.pk).update(
        monthly_ai_limit=limit, ai_calls=used, can_use_ai=can_use_ai
    )


def _run(*args):
    out = StringIO()
    call_command(COMMAND, *args, stdout=out)
    return out.getvalue()


def _queued_ids(mock_summary_task):
    return [c.args[0] for c in mock_summary_task.call_args_list]


@pytest.mark.django_db
class TestBackfillAiSummaryTargets:
    """只排入缺漏摘要且有評論的店家"""

    def test_only_missing_or_blank_summary_with_reviews_are_queued(self, mock_summary_task):
        _set_system_quota(limit=50)
        null_summary = CafeFactory(reviews=['好喝'], ai_summary=None)
        empty_summary = CafeFactory(reviews=['好喝'], ai_summary='')
        blank_summary = CafeFactory(reviews=['好喝'], ai_summary='  \n ')
        CafeFactory(reviews=['好喝'], ai_summary='已有摘要')
        CafeFactory(reviews=[], ai_summary=None)
        CafeFactory(reviews=None, ai_summary=None)

        _run()

        assert _queued_ids(mock_summary_task) == [null_summary.id, empty_summary.id, blank_summary.id]

    def test_no_targets_queues_nothing(self, mock_summary_task):
        _set_system_quota(limit=50)
        CafeFactory(reviews=['好喝'], ai_summary='已有摘要')

        output = _run()

        mock_summary_task.assert_not_called()
        assert '0' in output

    def test_does_not_modify_cafes(self, mock_summary_task):
        """command 只負責排入任務，不直接改寫任何店家資料"""
        _set_system_quota(limit=50)
        cafe = CafeFactory(reviews=['好喝'], ai_summary='')

        _run()

        cafe.refresh_from_db()
        assert cafe.ai_summary == ''


@pytest.mark.django_db
class TestBackfillAiSummaryOptions:

    def test_dry_run_queues_nothing_and_reports_count(self, mock_summary_task):
        _set_system_quota(limit=50)
        CafeFactory.create_batch(3, reviews=['好喝'], ai_summary=None)

        output = _run('--dry-run')

        mock_summary_task.assert_not_called()
        assert '3' in output

    def test_dry_run_does_not_acquire_locks(self, mock_summary_task):
        """試跑不佔用防重複的鎖，緊接著正式執行仍會排入"""
        _set_system_quota(limit=50)
        CafeFactory(reviews=['好喝'], ai_summary=None)

        _run('--dry-run')
        _run()

        assert mock_summary_task.call_count == 1

    def test_limit_caps_queued_count_in_id_order(self, mock_summary_task):
        _set_system_quota(limit=50)
        cafes = CafeFactory.create_batch(5, reviews=['好喝'], ai_summary=None)

        _run('--limit', '2')

        assert _queued_ids(mock_summary_task) == [cafes[0].id, cafes[1].id]

    def test_limit_zero_queues_nothing(self, mock_summary_task):
        _set_system_quota(limit=50)
        CafeFactory(reviews=['好喝'], ai_summary=None)

        _run('--limit', '0')

        mock_summary_task.assert_not_called()

    @pytest.mark.parametrize('option', ['--limit', '--interval'])
    def test_negative_values_rejected(self, option, mock_summary_task):
        with pytest.raises(CommandError):
            _run(option, '-1')
        mock_summary_task.assert_not_called()

    def test_default_interval_stays_under_groq_tpm(self, mock_sleep, mock_summary_task):
        """未指定 --interval 時預設 25 秒：Groq gpt-oss-20b TPM 上限 8000、每次摘要約 2–3k tokens，
        每分鐘最多約 3 筆；實測 2 秒間隔時 50 筆有 37 筆 429 失敗"""
        _set_system_quota(limit=50)
        CafeFactory.create_batch(2, reviews=['好喝'], ai_summary=None)

        _run()

        mock_sleep.assert_called_once_with(25.0)

    def test_sleeps_interval_between_queued_tasks(self, mock_sleep, mock_summary_task):
        """每筆之間 sleep，最後一筆之後不 sleep"""
        _set_system_quota(limit=50)
        CafeFactory.create_batch(3, reviews=['好喝'], ai_summary=None)

        _run('--interval', '1.5')

        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(1.5)


@pytest.mark.django_db
class TestBackfillAiSummaryQuota:

    def test_caps_to_remaining_quota_and_warns(self, mock_summary_task):
        _set_system_quota(limit=10, used=8)
        CafeFactory.create_batch(5, reviews=['好喝'], ai_summary=None)

        output = _run()

        assert mock_summary_task.call_count == 2
        assert '額度' in output

    def test_quota_exhausted_queues_nothing(self, mock_summary_task):
        _set_system_quota(limit=10, used=10)
        CafeFactory(reviews=['好喝'], ai_summary=None)

        output = _run()

        mock_summary_task.assert_not_called()
        assert '額度' in output

    def test_quota_disabled_queues_nothing(self, mock_summary_task):
        _set_system_quota(limit=10, used=0, can_use_ai=False)
        CafeFactory(reviews=['好喝'], ai_summary=None)

        _run()

        mock_summary_task.assert_not_called()

    def test_limit_smaller_than_quota_wins(self, mock_summary_task):
        _set_system_quota(limit=10, used=0)
        CafeFactory.create_batch(5, reviews=['好喝'], ai_summary=None)

        _run('--limit', '3')

        assert mock_summary_task.call_count == 3

    def test_command_itself_does_not_consume_quota(self, mock_summary_task):
        """額度在任務內扣除，command 只查詢不扣"""
        _set_system_quota(limit=10, used=0)
        CafeFactory.create_batch(2, reviews=['好喝'], ai_summary=None)

        _run()

        user_id = ApiUsageService.get_system_ai_user_id()
        assert ApiUsageService.get_remaining_ai_calls(user_id) == 10


@pytest.mark.django_db
class TestBackfillAiSummaryIdempotency:

    def test_rerun_does_not_requeue_recently_queued(self, mock_summary_task):
        _set_system_quota(limit=50)
        CafeFactory.create_batch(2, reviews=['好喝'], ai_summary=None)

        _run()
        _run()

        assert mock_summary_task.call_count == 2

    def test_locked_cafes_do_not_count_toward_limit(self, mock_summary_task):
        """已排入（鎖住）的店家被跳過時，不佔用 --limit 名額"""
        _set_system_quota(limit=50)
        cafes = CafeFactory.create_batch(3, reviews=['好喝'], ai_summary=None)
        LockService.acquire(str(cafes[0].id), 'ai_summary_backfill', ttl=600)

        _run('--limit', '2')

        assert _queued_ids(mock_summary_task) == [cafes[1].id, cafes[2].id]


@pytest.mark.django_db
class TestBackfillAiSummaryFailure:

    def test_enqueue_failure_releases_lock_and_raises(self, mock_summary_task):
        _set_system_quota(limit=50)
        first, second, third = CafeFactory.create_batch(3, reviews=['好喝'], ai_summary=None)
        mock_summary_task.side_effect = [None, ConnectionError('broker down'), None]

        with pytest.raises(CommandError) as exc_info:
            _run()

        assert '1' in str(exc_info.value)
        assert mock_summary_task.call_count == 2
        # 失敗的店家鎖已釋放，可再次取得；成功排入的店家鎖仍在
        assert LockService.acquire(str(second.id), 'ai_summary_backfill', ttl=600) is True
        assert LockService.acquire(str(first.id), 'ai_summary_backfill', ttl=600) is False

    def test_enqueue_failure_is_logged(self, mock_summary_task, caplog):
        _set_system_quota(limit=50)
        CafeFactory(reviews=['好喝'], ai_summary=None)
        mock_summary_task.side_effect = ConnectionError('broker down')

        with pytest.raises(CommandError):
            _run()

        assert any('broker down' in r.getMessage() for r in caplog.records)
