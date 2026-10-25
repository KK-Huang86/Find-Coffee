import logging
from datetime import timedelta

import pytest
from unittest.mock import patch
from django.utils import timezone

from cafe.models import Cafe
from cafe.services.cafe_refresh import (
    is_cafe_stale,
    refresh_cafe_if_stale,
    refresh_cafe_now,
    refresh_photo_reference,
)
from cafe.tests.factories import CafeFactory


@pytest.fixture
def mock_refresh(mocker):
    """Mock refresh_cafe_data，預設模擬成功並更新 DB 中的店名"""
    def fake_refresh(cafe_id, trigger_photo_upload=True):
        Cafe.objects.filter(id=cafe_id).update(name='更新後店名', last_refreshed=timezone.now())
        return {'status': 'success', 'cafe_id': cafe_id}

    return mocker.patch('cafe.services.cafe_refresh.refresh_cafe_data', side_effect=fake_refresh)


@pytest.mark.django_db
class TestIsCafeStale:
    """測試 is_cafe_stale"""

    def test_never_refreshed_is_stale(self):
        """last_refreshed 為 None 視為過期"""
        assert is_cafe_stale(CafeFactory(last_refreshed=None)) is True

    def test_older_than_30_days_is_stale(self):
        """超過 30 天視為過期"""
        assert is_cafe_stale(CafeFactory(last_refreshed=timezone.now() - timedelta(days=31))) is True

    def test_exactly_30_days_is_stale(self):
        """剛好 30 天視為過期（邊界）"""
        now = timezone.now()
        cafe = CafeFactory(last_refreshed=now - timedelta(days=30))
        assert is_cafe_stale(cafe, now=now) is True

    def test_within_30_days_is_not_stale(self):
        """未滿 30 天不過期"""
        now = timezone.now()
        cafe = CafeFactory(last_refreshed=now - timedelta(days=29, hours=23))
        assert is_cafe_stale(cafe, now=now) is False

    def test_just_refreshed_is_not_stale(self):
        """剛更新過不過期"""
        assert is_cafe_stale(CafeFactory(last_refreshed=timezone.now())) is False


@pytest.mark.django_db
class TestRefreshCafeNow:
    """測試 refresh_cafe_now"""

    def test_success_refreshes_without_triggering_photo_upload(self, mock_refresh):
        """成功時以 trigger_photo_upload=False 呼叫 refresh_cafe_data，回傳 True"""
        cafe = CafeFactory(last_refreshed=None)

        assert refresh_cafe_now(cafe) is True
        mock_refresh.assert_called_once_with(cafe.id, trigger_photo_upload=False)

    def test_success_reloads_cafe_from_db(self, mock_refresh):
        """成功後傳入的 cafe 物件反映 DB 最新資料"""
        cafe = CafeFactory(name='舊店名', last_refreshed=None)

        refresh_cafe_now(cafe)

        assert cafe.name == '更新後店名'
        assert cafe.last_refreshed is not None

    def test_second_call_within_ttl_is_skipped(self, mock_refresh):
        """同一間店在 lock TTL 內重複呼叫，只刷新一次"""
        cafe = CafeFactory(last_refreshed=None)

        assert refresh_cafe_now(cafe) is True
        assert refresh_cafe_now(cafe) is False
        assert mock_refresh.call_count == 1

    def test_lock_is_per_cafe(self, mock_refresh):
        """不同店家的 lock 互不影響"""
        cafe_a = CafeFactory(last_refreshed=None)
        cafe_b = CafeFactory(last_refreshed=None)

        assert refresh_cafe_now(cafe_a) is True
        assert refresh_cafe_now(cafe_b) is True
        assert mock_refresh.call_count == 2

    def test_lock_held_by_others_skips_refresh(self, mock_refresh, mocker):
        """lock 已被其他請求持有時不刷新，回傳 False，cafe 資料不變"""
        mocker.patch('cafe.services.cafe_refresh.LockService.acquire', return_value=False)
        cafe = CafeFactory(name='舊店名', last_refreshed=None)

        assert refresh_cafe_now(cafe) is False
        mock_refresh.assert_not_called()
        assert cafe.name == '舊店名'

    def test_lock_uses_refresh_action_with_600_seconds_ttl(self, mock_refresh, mocker):
        """lock key 為 (cafe.id, 'refresh')，TTL 600 秒"""
        mock_acquire = mocker.patch('cafe.services.cafe_refresh.LockService.acquire', return_value=True)
        cafe = CafeFactory(last_refreshed=None)

        refresh_cafe_now(cafe)

        mock_acquire.assert_called_once_with(str(cafe.id), 'refresh', ttl=600)

    def test_failed_status_returns_false_and_logs_warning(self, mocker, caplog):
        """refresh_cafe_data 回傳非 success 時回傳 False，並記錄 warning"""
        mocker.patch(
            'cafe.services.cafe_refresh.refresh_cafe_data',
            return_value={'status': 'failed', 'reason': 'no_api_response'},
        )
        cafe = CafeFactory(name='舊店名', last_refreshed=None)

        with caplog.at_level(logging.WARNING, logger='cafe.services.cafe_refresh'):
            assert refresh_cafe_now(cafe) is False

        assert cafe.name == '舊店名'
        assert any('no_api_response' in r.getMessage() for r in caplog.records)

    def test_exception_is_logged_not_raised(self, mocker, caplog):
        """refresh_cafe_data 拋出例外時不往外拋，回傳 False，並記錄 error"""
        mocker.patch('cafe.services.cafe_refresh.refresh_cafe_data', side_effect=RuntimeError('boom'))
        cafe = CafeFactory(last_refreshed=None)

        with caplog.at_level(logging.ERROR, logger='cafe.services.cafe_refresh'):
            assert refresh_cafe_now(cafe) is False

        errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert errors
        assert 'boom' in errors[0].getMessage()

    def test_failure_keeps_lock_so_retry_is_skipped(self, mocker):
        """刷新失敗後 lock 仍保留，TTL 內不再重打外部 API"""
        mock_refresh = mocker.patch(
            'cafe.services.cafe_refresh.refresh_cafe_data',
            return_value={'status': 'failed', 'reason': 'no_api_response'},
        )
        cafe = CafeFactory(last_refreshed=None)

        refresh_cafe_now(cafe)
        refresh_cafe_now(cafe)

        assert mock_refresh.call_count == 1


@pytest.mark.django_db
class TestRefreshCafeIfStale:
    """測試 refresh_cafe_if_stale"""

    def test_fresh_cafe_is_not_refreshed(self, mock_refresh):
        """未過期不刷新，回傳 False"""
        cafe = CafeFactory(last_refreshed=timezone.now())

        assert refresh_cafe_if_stale(cafe) is False
        mock_refresh.assert_not_called()

    def test_stale_cafe_is_refreshed(self, mock_refresh):
        """過期則刷新，回傳 True"""
        cafe = CafeFactory(last_refreshed=timezone.now() - timedelta(days=31))

        assert refresh_cafe_if_stale(cafe) is True
        mock_refresh.assert_called_once_with(cafe.id, trigger_photo_upload=False)

    def test_never_refreshed_cafe_is_refreshed(self, mock_refresh):
        """從未刷新過則刷新"""
        cafe = CafeFactory(last_refreshed=None)

        assert refresh_cafe_if_stale(cafe) is True


@pytest.mark.django_db
class TestRefreshPhotoReference:
    """測試 refresh_photo_reference"""

    def test_returns_new_reference_after_refresh(self):
        """刷新成功且 reference 改變時，回傳新 reference"""
        cafe = CafeFactory(place_id='p1', photo_reference='old_ref')

        def fake_refresh_now(c):
            Cafe.objects.filter(id=c.id).update(photo_reference='new_ref')
            c.refresh_from_db()
            return True

        with patch('cafe.services.cafe_refresh.refresh_cafe_now', side_effect=fake_refresh_now) as mock_now:
            result = refresh_photo_reference('p1', 'old_ref')

        assert result == 'new_ref'
        assert mock_now.call_args.args[0].id == cafe.id

    def test_returns_none_when_cafe_not_found(self):
        """找不到店家時回傳 None，不刷新"""
        with patch('cafe.services.cafe_refresh.refresh_cafe_now') as mock_now:
            result = refresh_photo_reference('missing', 'old_ref')

        assert result is None
        mock_now.assert_not_called()

    def test_returns_none_when_refresh_skipped_or_failed(self):
        """refresh_cafe_now 回傳 False（剛刷新過 / 失敗）時回傳 None"""
        CafeFactory(place_id='p1', photo_reference='old_ref')

        with patch('cafe.services.cafe_refresh.refresh_cafe_now', return_value=False):
            result = refresh_photo_reference('p1', 'old_ref')

        assert result is None

    def test_returns_none_and_warns_when_reference_unchanged(self, caplog):
        """刷新後 reference 未改變，代表不是過期問題，回傳 None 並記錄 warning"""
        CafeFactory(place_id='p1', photo_reference='old_ref')

        with patch('cafe.services.cafe_refresh.refresh_cafe_now', return_value=True), \
             caplog.at_level(logging.WARNING, logger='cafe.services.cafe_refresh'):
            result = refresh_photo_reference('p1', 'old_ref')

        assert result is None
        assert any('p1' in r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)

    def test_returns_none_when_refreshed_reference_is_empty(self):
        """刷新後店家已沒有照片（reference 為空），回傳 None"""
        CafeFactory(place_id='p1', photo_reference='old_ref')

        def fake_refresh_now(c):
            Cafe.objects.filter(id=c.id).update(photo_reference='')
            c.refresh_from_db()
            return True

        with patch('cafe.services.cafe_refresh.refresh_cafe_now', side_effect=fake_refresh_now):
            result = refresh_photo_reference('p1', 'old_ref')

        assert result is None

    def test_returns_none_when_place_id_empty(self):
        """place_id 為空時不查詢、不刷新"""
        with patch('cafe.services.cafe_refresh.refresh_cafe_now') as mock_now:
            result = refresh_photo_reference('', 'old_ref')

        assert result is None
        mock_now.assert_not_called()

    def test_exception_is_logged_and_returns_none(self, caplog):
        """查詢或刷新拋出例外時記錄 error，回傳 None，不中斷照片流程"""
        with patch('cafe.services.cafe_refresh.Cafe.objects.filter', side_effect=RuntimeError('db down')), \
             caplog.at_level(logging.ERROR, logger='cafe.services.cafe_refresh'):
            result = refresh_photo_reference('p1', 'old_ref')

        assert result is None
        assert any('db down' in r.getMessage() for r in caplog.records)
