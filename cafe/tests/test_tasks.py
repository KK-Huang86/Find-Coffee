import pytest

from cafe.tasks import download_and_upload_cafe_photo, generate_cafe_ai_summary
from cafe.tests.factories import CafeFactory


@pytest.mark.django_db
class TestDownloadAndUploadCafePhotoForce:
    """測試 download_and_upload_cafe_photo 的 force 參數（180 天照片更新用）"""

    def test_skips_when_already_uploaded_without_force(self, mocker):
        """預設（force=False）已有 S3 照片時跳過，不下載"""
        mock_get = mocker.patch('cafe.tasks.requests.get')
        cafe = CafeFactory(photo_reference='ref', photo_s3_url='https://cdn.example.com/old.jpg')

        result = download_and_upload_cafe_photo(cafe.id)

        assert result == {'status': 'skipped', 'reason': 'already_uploaded'}
        mock_get.assert_not_called()

    def test_force_downloads_even_when_already_uploaded(self, mocker):
        """force=True 時即使已有 S3 照片仍重新下載"""
        response = mocker.MagicMock()
        response.headers = {'Content-Type': 'text/html'}
        mock_get = mocker.patch('cafe.tasks.requests.get', return_value=response)
        cafe = CafeFactory(photo_reference='ref', photo_s3_url='https://cdn.example.com/old.jpg')

        result = download_and_upload_cafe_photo(cafe.id, force=True)

        mock_get.assert_called_once()
        assert result == {'status': 'failed', 'reason': 'invalid_content_type'}

    def test_downloads_from_google_photo_url_setting(self, mocker):
        """下載照片呼叫 GoogleAPI.PHOTO_URL（壓測時可指向 mock server）"""
        mocker.patch('cafe.tasks.GoogleAPI.PHOTO_URL', 'http://mock-google/maps/api/place/photo')
        response = mocker.MagicMock()
        response.headers = {'Content-Type': 'text/html'}
        mock_get = mocker.patch('cafe.tasks.requests.get', return_value=response)
        cafe = CafeFactory(photo_reference='ref1', photo_s3_url='')

        download_and_upload_cafe_photo(cafe.id)

        assert mock_get.call_args.args[0].startswith('http://mock-google/maps/api/place/photo?photo_reference=ref1')

    def test_force_still_skips_without_photo_reference(self, mocker):
        """force=True 但沒有 photo_reference 時仍跳過"""
        mock_get = mocker.patch('cafe.tasks.requests.get')
        cafe = CafeFactory(photo_reference='', photo_s3_url='https://cdn.example.com/old.jpg')

        result = download_and_upload_cafe_photo(cafe.id, force=True)

        assert result == {'status': 'skipped', 'reason': 'no_photo_reference'}
        mock_get.assert_not_called()


@pytest.mark.django_db
class TestGenerateCafeAiSummary:
    """測試 generate_cafe_ai_summary task"""

    SYSTEM_USER_ID = 999

    def _mock_quota(self, mocker, can_increment=True):
        mocker.patch('cafe.tasks.ApiUsageService.get_system_ai_user_id', return_value=self.SYSTEM_USER_ID)
        mock_increment = mocker.patch(
            'cafe.tasks.ApiUsageService.try_increment_ai_calls', return_value=can_increment
        )
        mock_revert = mocker.patch('cafe.tasks.ApiUsageService.revert_ai_call')
        return mock_increment, mock_revert

    def test_cafe_not_found(self, mocker):
        """cafe_id 不存在時，回傳 cafe_not_found，不拋未處理例外"""
        mock_summarize = mocker.patch('cafe.tasks.GroqAPI.summarize_for_search')

        result = generate_cafe_ai_summary(cafe_id=99999)

        assert result == {'status': 'failed', 'reason': 'cafe_not_found'}
        mock_summarize.assert_not_called()

    def test_no_reviews_skips_without_calling_groq_or_quota(self, mocker):
        """reviews 為空清單時跳過，不呼叫 Groq、不消耗額度"""
        cafe = CafeFactory(reviews=[])
        mock_increment, _ = self._mock_quota(mocker)
        mock_summarize = mocker.patch('cafe.tasks.GroqAPI.summarize_for_search')

        result = generate_cafe_ai_summary(cafe_id=cafe.id)

        assert result == {'status': 'skipped', 'reason': 'no_reviews'}
        mock_increment.assert_not_called()
        mock_summarize.assert_not_called()

    def test_quota_exhausted_skips_without_calling_groq(self, mocker):
        """額度用盡時跳過，不呼叫 Groq"""
        cafe = CafeFactory(reviews=['環境安靜'])
        self._mock_quota(mocker, can_increment=False)
        mock_summarize = mocker.patch('cafe.tasks.GroqAPI.summarize_for_search')

        result = generate_cafe_ai_summary(cafe_id=cafe.id)

        assert result == {'status': 'skipped', 'reason': 'quota_exceeded'}
        mock_summarize.assert_not_called()

    def test_success_updates_ai_summary_without_touching_other_fields(self, mocker):
        """Groq 呼叫成功時，ai_summary 被寫入，且不影響其他欄位"""
        cafe = CafeFactory(reviews=['環境安靜'], name='原始名稱', favorite_count=3)
        self._mock_quota(mocker)
        mocker.patch('cafe.tasks.GroqAPI.summarize_for_search', return_value='適合安靜工作的咖啡店。')

        result = generate_cafe_ai_summary(cafe_id=cafe.id)

        cafe.refresh_from_db()
        assert result == {'status': 'success', 'cafe_id': cafe.id}
        assert cafe.ai_summary == '適合安靜工作的咖啡店。'
        assert cafe.name == '原始名稱'
        assert cafe.favorite_count == 3

    def test_groq_failure_reverts_quota_and_keeps_original_ai_summary(self, mocker):
        """Groq 呼叫失敗（回傳 None）時，revert 額度且 ai_summary 維持原值"""
        cafe = CafeFactory(reviews=['環境安靜'], ai_summary='舊摘要')
        _, mock_revert = self._mock_quota(mocker)
        mocker.patch('cafe.tasks.GroqAPI.summarize_for_search', return_value=None)

        result = generate_cafe_ai_summary(cafe_id=cafe.id)

        cafe.refresh_from_db()
        assert result == {'status': 'failed', 'reason': 'groq_error'}
        mock_revert.assert_called_once_with(self.SYSTEM_USER_ID)
        assert cafe.ai_summary == '舊摘要'

    def test_repeated_execution_is_idempotent(self, mocker):
        """同一 cafe_id 重複執行兩次，最終 ai_summary 只反映最後一次成功結果"""
        cafe = CafeFactory(reviews=['環境安靜'])
        self._mock_quota(mocker)
        mock_summarize = mocker.patch('cafe.tasks.GroqAPI.summarize_for_search')

        mock_summarize.return_value = '第一次摘要'
        generate_cafe_ai_summary(cafe_id=cafe.id)

        mock_summarize.return_value = '第二次摘要'
        generate_cafe_ai_summary(cafe_id=cafe.id)

        cafe.refresh_from_db()
        assert cafe.ai_summary == '第二次摘要'
