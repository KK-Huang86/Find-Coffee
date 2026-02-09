import pytest
from datetime import timedelta
from django.utils import timezone

from cafe.tasks import refresh_cafe_data
from cafe.tests.factories import CafeFactory


@pytest.mark.django_db
class TestRefreshCafeData:
    """測試 refresh_cafe_data task"""

    def test_cafe_not_found(self, mock_google_api):
        """cafe_id 不存在時，返回 cafe_not_found"""
        result = refresh_cafe_data(cafe_id=99999)

        assert result == {'status': 'failed', 'reason': 'cafe_not_found'}
        mock_google_api.assert_not_called()

    def test_api_no_response(self, mock_google_api):
        """GoogleAPI 返回空 dict 時，返回 no_api_response"""
        cafe = CafeFactory()
        mock_google_api.return_value = {}

        result = refresh_cafe_data(cafe_id=cafe.id)

        assert result == {'status': 'failed', 'reason': 'no_api_response'}

    def test_update_fields_success(self, mock_google_api, mock_photo_task):
        """API 返回完整資料時，cafe 各欄位正確更新"""
        cafe = CafeFactory(
            name='舊名稱',
            rating=None,
            photo_s3_url='https://example.com/photo.jpg',  # 有照片，不觸發更新
            photo_updated_at=timezone.now(),
        )

        # 從 google map 拉到的新資料
        mock_google_api.return_value = {
            'name': '新名稱',
            'address': '新地址',
            'phone': '02-1234-5678',
            'rating': 4.8,
            'user_ratings_total': 200,
            'website': 'https://example.com',
            'google_maps': 'https://maps.google.com/xxx',
        }

        result = refresh_cafe_data(cafe_id=cafe.id)

        cafe.refresh_from_db()
        assert result['status'] == 'success'
        assert cafe.name == '新名稱'
        assert cafe.address == '新地址'
        assert cafe.phone == '02-1234-5678'
        assert float(cafe.rating) == 4.8
        assert cafe.user_ratings_total == 200

    def test_partial_update_none_ignored(self, mock_google_api, mock_photo_task):
        """API 部分欄位為 None 時，只更新非 None 欄位，原值保留"""
        cafe = CafeFactory(
            name='原始名稱',
            phone='原始電話',
            photo_s3_url='https://example.com/photo.jpg',
            photo_updated_at=timezone.now(),
        )
        mock_google_api.return_value = {
            'name': '新名稱',
            'phone': None,  # None 應該被忽略
            'rating': None,
        }

        refresh_cafe_data(cafe_id=cafe.id)

        cafe.refresh_from_db()
        assert cafe.name == '新名稱'
        assert cafe.phone == '原始電話'  # 保留原值

    def test_trigger_photo_upload_no_s3_url(self, mock_google_api, mock_photo_task):
        """無 photo_s3_url 時，觸發 download_and_upload_cafe_photo"""
        cafe = CafeFactory(photo_s3_url='')  # 沒有 S3 照片
        mock_google_api.return_value = {'name': '咖啡店'}

        refresh_cafe_data(cafe_id=cafe.id)

        mock_photo_task.assert_called_once_with(cafe.id)

    def test_trigger_photo_upload_expired(self, mock_google_api, mock_photo_task):
        """photo_updated_at 超過 180 天時，觸發照片更新"""
        cafe = CafeFactory(
            photo_s3_url='https://example.com/old.jpg',
            photo_updated_at=timezone.now() - timedelta(days=181),  # 超過 180 天
        )
        mock_google_api.return_value = {'name': '咖啡店'}

        refresh_cafe_data(cafe_id=cafe.id)

        mock_photo_task.assert_called_once_with(cafe.id)

    def test_no_photo_upload_recent(self, mock_google_api, mock_photo_task):
        """photo_updated_at 未超過 180 天時，不觸發照片更新"""
        cafe = CafeFactory(
            photo_s3_url='https://example.com/photo.jpg',
            photo_updated_at=timezone.now() - timedelta(days=30),  # 30 天前，未過期
        )
        mock_google_api.return_value = {'name': '咖啡店'}

        refresh_cafe_data(cafe_id=cafe.id)

        mock_photo_task.assert_not_called()
