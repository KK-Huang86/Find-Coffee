import logging
from datetime import timedelta

import pytest
from unittest.mock import patch
from django.db import DataError
from django.utils import timezone

from cafe.models import Cafe
from cafe.services.cafe_refresh import (
    is_cafe_stale,
    refresh_threshold,
    refresh_cafe_if_stale,
    refresh_cafe_now,
    refresh_photo_reference,
)
from cafe.tests.factories import CafeFactory


@pytest.fixture
def mock_google(mocker):
    """Mock Places Detail，預設回傳新的店名"""
    return mocker.patch(
        'cafe.services.cafe_refresh.GoogleAPI.get_shop_detail',
        return_value={'name': '更新後店名'},
    )


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

    # 商業邏輯變更（add-cache-protection）：過期門檻由固定 30 天改為依 place_id 分散在 25～30 天（防快取雪崩），
    # 「29 天 23 小時一定不過期」不再成立，改為驗證「略低於自己的門檻不過期」「達到門檻過期」
    def test_just_below_own_threshold_is_not_stale(self):
        """略低於自己的門檻時不過期"""
        now = timezone.now()
        cafe = CafeFactory()
        cafe.last_refreshed = now - refresh_threshold(cafe) + timedelta(seconds=1)
        assert is_cafe_stale(cafe, now=now) is False

    def test_reaching_own_threshold_is_stale(self):
        """達到自己的門檻時過期（邊界）"""
        now = timezone.now()
        cafe = CafeFactory()
        cafe.last_refreshed = now - refresh_threshold(cafe)
        assert is_cafe_stale(cafe, now=now) is True

    @pytest.mark.parametrize('place_id', ['a', 'ChIJN1t_tDeuEmsRUsoyG83frY4', 'pid_0', 'pid_99'])
    def test_never_exceeds_30_days_without_refresh(self, place_id):
        """任何店家達到 30 天都一定過期"""
        now = timezone.now()
        cafe = CafeFactory(place_id=place_id, last_refreshed=now - timedelta(days=30))
        assert is_cafe_stale(cafe, now=now) is True


@pytest.mark.django_db
class TestRefreshThreshold:
    """測試 refresh_threshold：依 place_id 分散在 25～30 天（防快取雪崩）"""

    def test_within_25_to_30_days(self):
        """門檻介於 25 天到 30 天"""
        for i in range(200):
            threshold = refresh_threshold(CafeFactory.build(place_id=f'pid_{i}'))
            assert timedelta(days=25) <= threshold <= timedelta(days=30)

    def test_same_place_id_is_deterministic(self):
        """同一間店的門檻固定，不會這次過期、下次又不過期"""
        cafe = CafeFactory.build(place_id='ChIJN1t_tDeuEmsRUsoyG83frY4')
        assert len({refresh_threshold(cafe) for _ in range(20)}) == 1

    def test_batch_is_spread(self):
        """100 間不同店家的門檻分布在多個值"""
        thresholds = {refresh_threshold(CafeFactory.build(place_id=f'pid_{i}')) for i in range(100)}
        assert len(thresholds) >= 50

    @pytest.mark.parametrize('place_id', ['', None])
    def test_missing_place_id_uses_30_days(self, place_id):
        """沒有 place_id 時退回 30 天，不拋例外"""
        assert refresh_threshold(CafeFactory.build(place_id=place_id)) == timedelta(days=30)

    def test_just_refreshed_is_not_stale(self):
        """剛更新過不過期"""
        assert is_cafe_stale(CafeFactory(last_refreshed=timezone.now())) is False


@pytest.mark.django_db
class TestRefreshCafeNow:
    """測試 refresh_cafe_now：lock、失敗回退"""

    def test_success_calls_google_with_place_id_and_returns_true(self, mock_google):
        """成功時以 place_id 呼叫 Places Detail，回傳 True"""
        cafe = CafeFactory(last_refreshed=None)

        assert refresh_cafe_now(cafe) is True
        mock_google.assert_called_once_with(cafe.place_id)

    def test_success_updates_cafe_object_and_db(self, mock_google):
        """成功後傳入的 cafe 物件與 DB 皆為最新資料，last_refreshed 更新"""
        cafe = CafeFactory(name='舊店名', last_refreshed=None)

        refresh_cafe_now(cafe)

        assert cafe.name == '更新後店名'
        assert cafe.last_refreshed is not None
        assert Cafe.objects.get(id=cafe.id).name == '更新後店名'

    def test_second_call_within_ttl_is_skipped(self, mock_google):
        """同一間店在 lock TTL 內重複呼叫，只刷新一次"""
        cafe = CafeFactory(last_refreshed=None)

        assert refresh_cafe_now(cafe) is True
        assert refresh_cafe_now(cafe) is False
        assert mock_google.call_count == 1

    def test_lock_is_per_cafe(self, mock_google):
        """不同店家的 lock 互不影響"""
        cafe_a = CafeFactory(last_refreshed=None)
        cafe_b = CafeFactory(last_refreshed=None)

        assert refresh_cafe_now(cafe_a) is True
        assert refresh_cafe_now(cafe_b) is True
        assert mock_google.call_count == 2

    def test_lock_held_by_others_skips_refresh(self, mock_google, mocker):
        """lock 已被其他請求持有時不刷新，回傳 False，cafe 資料不變"""
        mocker.patch('cafe.services.cafe_refresh.LockService.acquire', return_value=False)
        cafe = CafeFactory(name='舊店名', last_refreshed=None)

        assert refresh_cafe_now(cafe) is False
        mock_google.assert_not_called()
        assert cafe.name == '舊店名'

    def test_lock_uses_refresh_action_with_600_seconds_ttl(self, mock_google, mocker):
        """lock key 為 (cafe.id, 'refresh')，TTL 600 秒"""
        mock_acquire = mocker.patch('cafe.services.cafe_refresh.LockService.acquire', return_value=True)
        cafe = CafeFactory(last_refreshed=None)

        refresh_cafe_now(cafe)

        mock_acquire.assert_called_once_with(str(cafe.id), 'refresh', ttl=600)

    def test_no_api_response_returns_false_and_logs_warning(self, mock_google, caplog):
        """Places Detail 回傳空資料時回傳 False，資料與 last_refreshed 不變，記錄 warning"""
        mock_google.return_value = {}
        cafe = CafeFactory(name='舊店名', last_refreshed=None)

        with caplog.at_level(logging.WARNING, logger='cafe.services.cafe_refresh'):
            assert refresh_cafe_now(cafe) is False

        db_cafe = Cafe.objects.get(id=cafe.id)
        assert db_cafe.name == '舊店名'
        assert db_cafe.last_refreshed is None
        assert any(cafe.place_id in r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)

    def test_google_exception_is_logged_not_raised(self, mock_google, caplog):
        """Places Detail 拋出例外時不往外拋，回傳 False，並記錄 error"""
        mock_google.side_effect = RuntimeError('boom')
        cafe = CafeFactory(last_refreshed=None)

        with caplog.at_level(logging.ERROR, logger='cafe.services.cafe_refresh'):
            assert refresh_cafe_now(cafe) is False

        errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert errors
        assert 'boom' in errors[0].getMessage()

    def test_save_error_does_not_partially_write(self, mock_google, mocker, caplog):
        """寫入 DB 失敗（例如欄位過長）時回傳 False、記錄 error，DB 維持原資料"""
        mock_google.return_value = {'name': '新店名', 'website': 'https://example.com/' + 'a' * 300}
        cafe = CafeFactory(name='舊店名', last_refreshed=None)
        mocker.patch.object(Cafe, 'save', side_effect=DataError('value too long'))

        with caplog.at_level(logging.ERROR, logger='cafe.services.cafe_refresh'):
            assert refresh_cafe_now(cafe) is False

        assert Cafe.objects.filter(id=cafe.id).values_list('name', flat=True).get() == '舊店名'
        assert cafe.name == '舊店名'  # 記憶體中的物件也要回復，呼叫端才不會拿到半套新資料
        assert any('value too long' in r.getMessage() for r in caplog.records)

    def test_failure_keeps_lock_so_retry_is_skipped(self, mock_google):
        """刷新失敗後 lock 仍保留，TTL 內不再重打外部 API"""
        mock_google.return_value = {}
        cafe = CafeFactory(last_refreshed=None)

        refresh_cafe_now(cafe)
        refresh_cafe_now(cafe)

        assert mock_google.call_count == 1


@pytest.mark.django_db
class TestRefreshCafeNowFieldUpdate:
    """測試 refresh_cafe_now 的欄位更新（原 refresh_cafe_data task 的行為）"""

    def test_updates_all_fields(self, mock_google):
        """API 返回完整資料時，cafe 各欄位正確更新"""
        cafe = CafeFactory(name='舊名稱', rating=None, last_refreshed=None)
        mock_google.return_value = {
            'name': '新名稱',
            'address': '新地址',
            'phone': '02-1234-5678',
            'rating': 4.8,
            'user_ratings_total': 200,
            'website': 'https://example.com',
            'google_maps': 'https://maps.google.com/xxx',
            'photo_reference': 'new_ref',
            'reviews': ['新評論'],
        }

        assert refresh_cafe_now(cafe) is True

        cafe.refresh_from_db()
        assert cafe.name == '新名稱'
        assert cafe.address == '新地址'
        assert cafe.phone == '02-1234-5678'
        assert float(cafe.rating) == 4.8
        assert cafe.user_ratings_total == 200
        assert cafe.website == 'https://example.com'
        assert cafe.google_maps == 'https://maps.google.com/xxx'
        assert cafe.photo_reference == 'new_ref'
        assert cafe.reviews == ['新評論']

    def test_none_fields_keep_original_values(self, mock_google):
        """API 部分欄位為 None 時，只更新非 None 欄位，原值保留"""
        cafe = CafeFactory(name='原始名稱', phone='原始電話', last_refreshed=None)
        mock_google.return_value = {'name': '新名稱', 'phone': None, 'rating': None}

        refresh_cafe_now(cafe)

        cafe.refresh_from_db()
        assert cafe.name == '新名稱'
        assert cafe.phone == '原始電話'

    def test_triggers_ai_summary_when_reviews_changed(self, mock_google, mock_summary_task):
        """reviews 較刷新前有變化時，觸發摘要重新產生"""
        cafe = CafeFactory(reviews=['舊評論'], ai_summary='舊摘要', last_refreshed=None)
        mock_google.return_value = {'name': '咖啡店', 'reviews': ['新評論']}

        refresh_cafe_now(cafe)

        mock_summary_task.assert_called_once_with(cafe.id)

    def test_no_ai_summary_when_reviews_unchanged_and_summary_exists(self, mock_google, mock_summary_task):
        """reviews 未變化且已有 ai_summary 時，不觸發摘要重新產生"""
        cafe = CafeFactory(reviews=['相同評論'], ai_summary='已有摘要', last_refreshed=None)
        mock_google.return_value = {'name': '咖啡店', 'reviews': ['相同評論']}

        refresh_cafe_now(cafe)

        mock_summary_task.assert_not_called()

    def test_triggers_ai_summary_retry_when_summary_missing(self, mock_google, mock_summary_task):
        """ai_summary 為空值時，即使 reviews 未變化也觸發重試"""
        cafe = CafeFactory(reviews=['相同評論'], ai_summary=None, last_refreshed=None)
        mock_google.return_value = {'name': '咖啡店', 'reviews': ['相同評論']}

        refresh_cafe_now(cafe)

        mock_summary_task.assert_called_once_with(cafe.id)

    def test_failed_refresh_does_not_trigger_ai_summary(self, mock_google, mock_summary_task):
        """刷新失敗時不觸發摘要"""
        mock_google.return_value = {}
        cafe = CafeFactory(ai_summary=None, last_refreshed=None)

        refresh_cafe_now(cafe)

        mock_summary_task.assert_not_called()


@pytest.mark.django_db
class TestRefreshCafeNowPhotoRefresh:
    """測試 refresh_cafe_now 後的 180 天照片更新：以背景任務強制重新下載，不先清空舊 S3 照片"""

    S3_URL = 'https://cdn.example.com/cafe-photos/p.jpg'

    def test_expired_photo_queues_forced_download_and_keeps_old_s3_url(self, mock_google, mock_photo_task):
        """S3 照片超過 180 天：送出 force=True 的背景下載，舊 S3 URL 保留到新照片上傳完成"""
        cafe = CafeFactory(
            photo_s3_url=self.S3_URL,
            photo_updated_at=timezone.now() - timedelta(days=181),
            last_refreshed=None,
        )

        refresh_cafe_now(cafe)

        mock_photo_task.assert_called_once_with(cafe.id, force=True)
        cafe.refresh_from_db()
        assert cafe.photo_s3_url == self.S3_URL
        assert cafe.photo_updated_at is not None

    def test_exactly_180_days_queues_forced_download(self, mock_google, mock_photo_task):
        """剛好 180 天也視為過期（邊界）"""
        cafe = CafeFactory(
            photo_s3_url=self.S3_URL,
            photo_updated_at=timezone.now() - timedelta(days=180),
            last_refreshed=None,
        )

        refresh_cafe_now(cafe)

        mock_photo_task.assert_called_once_with(cafe.id, force=True)

    def test_recent_photo_does_not_queue_download(self, mock_google, mock_photo_task):
        """S3 照片未滿 180 天不重新下載"""
        cafe = CafeFactory(
            photo_s3_url=self.S3_URL,
            photo_updated_at=timezone.now() - timedelta(days=179),
            last_refreshed=None,
        )

        refresh_cafe_now(cafe)

        mock_photo_task.assert_not_called()

    def test_no_s3_photo_does_not_queue_download(self, mock_google, mock_photo_task):
        """沒有 S3 照片時不在這裡觸發上傳（由 get_photo_url 統一觸發）"""
        cafe = CafeFactory(photo_s3_url='', photo_updated_at=None, last_refreshed=None)

        refresh_cafe_now(cafe)

        mock_photo_task.assert_not_called()

    def test_s3_photo_without_updated_at_does_not_queue_download(self, mock_google, mock_photo_task):
        """有 S3 照片但 photo_updated_at 為空時，無法判斷是否過期，不重新下載"""
        cafe = CafeFactory(photo_s3_url=self.S3_URL, photo_updated_at=None, last_refreshed=None)

        refresh_cafe_now(cafe)

        mock_photo_task.assert_not_called()

    def test_failed_refresh_does_not_queue_download(self, mock_google, mock_photo_task):
        """資料刷新失敗時不檢查照片"""
        mock_google.return_value = {}
        cafe = CafeFactory(
            photo_s3_url=self.S3_URL,
            photo_updated_at=timezone.now() - timedelta(days=181),
            last_refreshed=None,
        )

        refresh_cafe_now(cafe)

        mock_photo_task.assert_not_called()


@pytest.mark.django_db
class TestRefreshCafeIfStale:
    """測試 refresh_cafe_if_stale"""

    def test_fresh_cafe_is_not_refreshed(self, mock_google):
        """未過期不刷新，回傳 False"""
        cafe = CafeFactory(last_refreshed=timezone.now())

        assert refresh_cafe_if_stale(cafe) is False
        mock_google.assert_not_called()

    def test_stale_cafe_is_refreshed(self, mock_google):
        """過期則刷新，回傳 True"""
        cafe = CafeFactory(last_refreshed=timezone.now() - timedelta(days=31))

        assert refresh_cafe_if_stale(cafe) is True
        mock_google.assert_called_once_with(cafe.place_id)

    def test_never_refreshed_cafe_is_refreshed(self, mock_google):
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
