import pytest
from unittest.mock import MagicMock, patch

from line_bot.builders.shop_flex_message import FlexMessageBuilder
from line_bot.tests.factories import CafeFactory


# FlexMessageBuilder.get_photo_url


class TestGetPhotoUrl:
    """測試 FlexMessageBuilder.get_photo_url"""

    def test_returns_s3_url_when_available(self):
        """photo_s3_url 有值時，直接回傳"""
        info = {'photo_s3_url': 'https://s3.example.com/photo.jpg', 'photo_reference': 'ref123', 'place_id': 'p1'}
        result = FlexMessageBuilder.get_photo_url(info)
        assert result == 'https://s3.example.com/photo.jpg'

    def test_resolves_google_photo_when_no_s3_url(self):
        """無 S3 URL 但有 photo_reference 時，解析 Google photo URL"""
        info = {'photo_s3_url': '', 'photo_reference': 'ref123', 'place_id': 'p1'}
        resolved = 'https://lh3.googleusercontent.com/photo.jpg'

        with patch.object(FlexMessageBuilder, 'resolve_photo_url', return_value=resolved) as mock_resolve, \
             patch.object(FlexMessageBuilder, '_trigger_s3_upload') as mock_upload:
            result = FlexMessageBuilder.get_photo_url(info)

        mock_resolve.assert_called_once()
        assert mock_resolve.call_args.args[0] == 'ref123'
        mock_upload.assert_called_once_with('p1')
        assert result == resolved

    def test_triggers_upload_even_when_resolved_to_default(self):
        """解析後得到預設圖時，仍觸發 S3 上傳（商業邏輯變更：背景快取觸發不再依賴同步解析是否成功，見 design.md Decision 2；此測試斷言由「不觸發」改為「觸發」，非遷就實作而修改）"""
        info = {'photo_s3_url': '', 'photo_reference': 'ref123', 'place_id': 'p1'}

        with patch.object(FlexMessageBuilder, 'resolve_photo_url', return_value=FlexMessageBuilder.DEFAULT_PHOTO_URL), \
             patch.object(FlexMessageBuilder, '_trigger_s3_upload') as mock_upload:
            FlexMessageBuilder.get_photo_url(info)

        mock_upload.assert_called_once_with('p1')

    def test_returns_default_when_no_photo_reference_or_s3(self):
        """photo_s3_url 和 photo_reference 皆為空時，回傳預設圖，且不觸發背景快取（無可用照片來源，不屬於「觸發條件與解析結果無關」規則的適用範圍，見 specs/cafe-photo-loading/spec.md）"""
        info = {'photo_s3_url': '', 'photo_reference': '', 'place_id': 'p1'}

        with patch.object(FlexMessageBuilder, '_trigger_s3_upload') as mock_upload:
            result = FlexMessageBuilder.get_photo_url(info)

        assert result == FlexMessageBuilder.DEFAULT_PHOTO_URL
        mock_upload.assert_not_called()

    @pytest.mark.django_db
    def test_accepts_cafe_model_object(self):
        """傳入 Cafe 物件時，轉換為 dict 處理"""
        cafe = CafeFactory(photo_s3_url='https://s3.example.com/cafe.jpg')
        result = FlexMessageBuilder.get_photo_url(cafe)
        assert result == 'https://s3.example.com/cafe.jpg'

    def test_skips_sync_resolve_when_allow_sync_resolve_false(self):
        """allow_sync_resolve=False 時，photo_s3_url 為空但有 photo_reference，不呼叫 resolve_photo_url，直接回傳預設圖"""
        info = {'photo_s3_url': '', 'photo_reference': 'ref123', 'place_id': 'p1'}

        with patch.object(FlexMessageBuilder, 'resolve_photo_url') as mock_resolve, \
             patch.object(FlexMessageBuilder, '_trigger_s3_upload'):
            result = FlexMessageBuilder.get_photo_url(info, allow_sync_resolve=False)

        mock_resolve.assert_not_called()
        assert result == FlexMessageBuilder.DEFAULT_PHOTO_URL

    def test_triggers_upload_even_when_sync_resolve_skipped(self):
        """allow_sync_resolve=False 時，即使跳過同步解析，仍觸發 S3 背景上傳"""
        info = {'photo_s3_url': '', 'photo_reference': 'ref123', 'place_id': 'p1'}

        with patch.object(FlexMessageBuilder, 'resolve_photo_url'), \
             patch.object(FlexMessageBuilder, '_trigger_s3_upload') as mock_upload:
            FlexMessageBuilder.get_photo_url(info, allow_sync_resolve=False)

        mock_upload.assert_called_once_with('p1')

    def test_allow_sync_resolve_true_explicit_matches_default(self):
        """allow_sync_resolve=True 顯式傳入時，行為與不傳（預設值）一致，皆會呼叫 resolve_photo_url"""
        info = {'photo_s3_url': '', 'photo_reference': 'ref123', 'place_id': 'p1'}
        resolved = 'https://lh3.googleusercontent.com/photo.jpg'

        with patch.object(FlexMessageBuilder, 'resolve_photo_url', return_value=resolved) as mock_resolve, \
             patch.object(FlexMessageBuilder, '_trigger_s3_upload'):
            result = FlexMessageBuilder.get_photo_url(info, allow_sync_resolve=True)

        mock_resolve.assert_called_once()
        assert mock_resolve.call_args.args[0] == 'ref123'
        assert result == resolved

    def test_s3_url_returned_regardless_of_allow_sync_resolve(self):
        """photo_s3_url 已有值時，無論 allow_sync_resolve 為 True 或 False，皆直接回傳該 S3 URL"""
        info = {'photo_s3_url': 'https://s3.example.com/photo.jpg', 'photo_reference': 'ref123', 'place_id': 'p1'}

        result_true = FlexMessageBuilder.get_photo_url(info, allow_sync_resolve=True)
        result_false = FlexMessageBuilder.get_photo_url(info, allow_sync_resolve=False)

        assert result_true == 'https://s3.example.com/photo.jpg'
        assert result_false == 'https://s3.example.com/photo.jpg'


class TestGetPhotoUrlRefreshOnRejectedReference:
    """測試 get_photo_url 在 reference 被拒絕時的刷新與重試接線"""

    def test_passes_on_rejected_callback_that_refreshes_this_cafe(self):
        """get_photo_url 傳給 resolve_photo_url 的 on_rejected 會以 (place_id, 舊 reference) 刷新"""
        info = {'photo_s3_url': '', 'photo_reference': 'old_ref', 'place_id': 'p1'}

        def fake_resolve(photo_reference, on_rejected=None):
            return f'https://lh3.googleusercontent.com/{on_rejected()}.jpg'

        with patch.object(FlexMessageBuilder, 'resolve_photo_url', side_effect=fake_resolve), \
             patch('line_bot.builders.shop_flex_message.refresh_photo_reference', return_value='new_ref') as mock_refresh, \
             patch.object(FlexMessageBuilder, '_trigger_s3_upload'):
            result = FlexMessageBuilder.get_photo_url(info)

        mock_refresh.assert_called_once_with('p1', 'old_ref')
        assert result == 'https://lh3.googleusercontent.com/new_ref.jpg'

    def test_triggers_s3_upload_once_even_when_refreshed(self):
        """reference 被拒並刷新重試後，背景上傳仍只觸發一次"""
        info = {'photo_s3_url': '', 'photo_reference': 'old_ref', 'place_id': 'p1'}

        def fake_resolve(photo_reference, on_rejected=None):
            on_rejected()
            return 'https://lh3.googleusercontent.com/new.jpg'

        with patch.object(FlexMessageBuilder, 'resolve_photo_url', side_effect=fake_resolve), \
             patch('line_bot.builders.shop_flex_message.refresh_photo_reference', return_value='new_ref'), \
             patch.object(FlexMessageBuilder, '_trigger_s3_upload') as mock_upload:
            FlexMessageBuilder.get_photo_url(info)

        mock_upload.assert_called_once_with('p1')

    def test_skipped_sync_resolve_never_refreshes(self):
        """allow_sync_resolve=False 時不解析、也不刷新"""
        info = {'photo_s3_url': '', 'photo_reference': 'old_ref', 'place_id': 'p1'}

        with patch('line_bot.builders.shop_flex_message.refresh_photo_reference') as mock_refresh, \
             patch.object(FlexMessageBuilder, '_trigger_s3_upload'):
            FlexMessageBuilder.get_photo_url(info, allow_sync_resolve=False)

        mock_refresh.assert_not_called()

# FlexMessageBuilder.resolve_photo_url


class TestResolvePhotoUrl:
    """測試 FlexMessageBuilder.resolve_photo_url"""

    def test_returns_default_for_empty_reference(self):
        """空字串 reference 直接回傳預設圖"""
        result = FlexMessageBuilder.resolve_photo_url('')
        assert result == FlexMessageBuilder.DEFAULT_PHOTO_URL

    def test_returns_resolved_url_on_success(self):
        """requests.head 成功時，回傳 response.url"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.url = 'https://lh3.googleusercontent.com/photo.jpg'

        with patch('line_bot.builders.shop_flex_message.requests.head', return_value=mock_response), \
             patch('line_bot.builders.shop_flex_message.config', return_value='fake_key'):
            result = FlexMessageBuilder.resolve_photo_url('valid_ref')

        assert result == 'https://lh3.googleusercontent.com/photo.jpg'

    def test_returns_default_when_status_not_200(self):
        """HTTP 狀態非 200 時，回傳預設圖"""
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch('line_bot.builders.shop_flex_message.requests.head', return_value=mock_response), \
             patch('line_bot.builders.shop_flex_message.config', return_value='fake_key'):
            result = FlexMessageBuilder.resolve_photo_url('some_ref')

        assert result == FlexMessageBuilder.DEFAULT_PHOTO_URL

    def test_uses_split_connect_and_read_timeout(self):
        """requests.head 使用 (connect, read) 分開的 timeout：連線 2 秒、讀取 4 秒"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.url = 'https://lh3.googleusercontent.com/photo.jpg'

        with patch('line_bot.builders.shop_flex_message.requests.head', return_value=mock_response) as mock_head, \
             patch('line_bot.builders.shop_flex_message.config', return_value='fake_key'):
            FlexMessageBuilder.resolve_photo_url('valid_ref')

        assert mock_head.call_args.kwargs['timeout'] == (2, 4)

    @pytest.mark.parametrize('status_code', [204, 302, 400, 403, 404, 500])
    def test_logs_warning_with_status_code_when_not_200(self, status_code, caplog):
        """HTTP 狀態非 200 時，記錄一筆 warning，內容包含 status code 與 photo_reference"""
        mock_response = MagicMock()
        mock_response.status_code = status_code

        with patch('line_bot.builders.shop_flex_message.requests.head', return_value=mock_response), \
             patch('line_bot.builders.shop_flex_message.config', return_value='fake_key'), \
             caplog.at_level('WARNING', logger='line_bot.builders.shop_flex_message'):
            result = FlexMessageBuilder.resolve_photo_url('some_ref')

        assert result == FlexMessageBuilder.DEFAULT_PHOTO_URL
        warnings = [r for r in caplog.records if r.levelname == 'WARNING']
        assert len(warnings) == 1
        assert str(status_code) in warnings[0].getMessage()
        assert 'some_ref' in warnings[0].getMessage()

    def test_non_200_log_does_not_leak_api_key(self, caplog):
        """非 200 的 log 不得包含 API key（photo API URL 內含 key，不可整串寫入 log）"""
        mock_response = MagicMock()
        mock_response.status_code = 403

        with patch('line_bot.builders.shop_flex_message.requests.head', return_value=mock_response), \
             patch('line_bot.builders.shop_flex_message.config', return_value='secret_key_123'), \
             caplog.at_level('WARNING', logger='line_bot.builders.shop_flex_message'):
            FlexMessageBuilder.resolve_photo_url('some_ref')

        assert all('secret_key_123' not in r.getMessage() for r in caplog.records)

    def test_does_not_log_warning_on_success(self, caplog):
        """200 成功時不記錄 warning"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.url = 'https://lh3.googleusercontent.com/photo.jpg'

        with patch('line_bot.builders.shop_flex_message.requests.head', return_value=mock_response), \
             patch('line_bot.builders.shop_flex_message.config', return_value='fake_key'), \
             caplog.at_level('WARNING', logger='line_bot.builders.shop_flex_message'):
            FlexMessageBuilder.resolve_photo_url('valid_ref')

        assert not [r for r in caplog.records if r.levelname == 'WARNING']

    def test_uses_google_photo_url_setting(self):
        """照片解析呼叫 GoogleAPI.PHOTO_URL（壓測時可指向 mock server）"""
        from integrations.google.api import GoogleAPI

        with patch.object(GoogleAPI, 'PHOTO_URL', 'http://mock-google/maps/api/place/photo'), \
             patch('line_bot.builders.shop_flex_message.requests.head',
                   return_value=self._response(200, 'http://mock-google/image.jpg')) as mock_head, \
             patch('line_bot.builders.shop_flex_message.config', return_value='fake_key'):
            FlexMessageBuilder.resolve_photo_url('ref1')

        assert mock_head.call_args.args[0].startswith('http://mock-google/maps/api/place/photo?photo_reference=ref1')

    def _response(self, status_code, url=''):
        resp = MagicMock()
        resp.status_code = status_code
        resp.url = url
        return resp

    @pytest.mark.parametrize('status_code', [400, 403])
    def test_rejected_reference_calls_on_rejected_and_retries_with_new_reference(self, status_code):
        """400/403 時呼叫 on_rejected 取得新 reference，並以新 reference 重新解析一次"""
        responses = [self._response(status_code), self._response(200, 'https://lh3.googleusercontent.com/new.jpg')]
        on_rejected = MagicMock(return_value='new_ref')

        with patch('line_bot.builders.shop_flex_message.requests.head', side_effect=responses) as mock_head, \
             patch('line_bot.builders.shop_flex_message.config', return_value='fake_key'):
            result = FlexMessageBuilder.resolve_photo_url('old_ref', on_rejected=on_rejected)

        assert result == 'https://lh3.googleusercontent.com/new.jpg'
        on_rejected.assert_called_once_with()
        assert mock_head.call_count == 2
        assert 'photo_reference=new_ref' in mock_head.call_args_list[1].args[0]

    def test_retries_at_most_once_when_new_reference_also_rejected(self):
        """新 reference 仍被拒時不再重試，回傳預設圖"""
        on_rejected = MagicMock(return_value='new_ref')

        with patch('line_bot.builders.shop_flex_message.requests.head', return_value=self._response(403)) as mock_head, \
             patch('line_bot.builders.shop_flex_message.config', return_value='fake_key'):
            result = FlexMessageBuilder.resolve_photo_url('old_ref', on_rejected=on_rejected)

        assert result == FlexMessageBuilder.DEFAULT_PHOTO_URL
        assert mock_head.call_count == 2
        on_rejected.assert_called_once()

    def test_no_retry_when_on_rejected_returns_none(self):
        """on_rejected 拿不到新 reference 時不重試，回傳預設圖"""
        on_rejected = MagicMock(return_value=None)

        with patch('line_bot.builders.shop_flex_message.requests.head', return_value=self._response(400)) as mock_head, \
             patch('line_bot.builders.shop_flex_message.config', return_value='fake_key'):
            result = FlexMessageBuilder.resolve_photo_url('old_ref', on_rejected=on_rejected)

        assert result == FlexMessageBuilder.DEFAULT_PHOTO_URL
        assert mock_head.call_count == 1

    @pytest.mark.parametrize('status_code', [204, 302, 404, 429, 500])
    def test_other_non_200_does_not_call_on_rejected(self, status_code):
        """400/403 以外的非 200 不觸發刷新"""
        on_rejected = MagicMock(return_value='new_ref')

        with patch('line_bot.builders.shop_flex_message.requests.head', return_value=self._response(status_code)), \
             patch('line_bot.builders.shop_flex_message.config', return_value='fake_key'):
            result = FlexMessageBuilder.resolve_photo_url('old_ref', on_rejected=on_rejected)

        assert result == FlexMessageBuilder.DEFAULT_PHOTO_URL
        on_rejected.assert_not_called()

    def test_request_exception_does_not_call_on_rejected(self):
        """逾時等請求例外不觸發刷新"""
        import requests as req_lib
        on_rejected = MagicMock(return_value='new_ref')

        with patch('line_bot.builders.shop_flex_message.requests.head', side_effect=req_lib.Timeout('slow')), \
             patch('line_bot.builders.shop_flex_message.config', return_value='fake_key'):
            result = FlexMessageBuilder.resolve_photo_url('old_ref', on_rejected=on_rejected)

        assert result == FlexMessageBuilder.DEFAULT_PHOTO_URL
        on_rejected.assert_not_called()

    def test_success_does_not_call_on_rejected(self):
        """200 成功時不觸發刷新"""
        on_rejected = MagicMock(return_value='new_ref')

        with patch('line_bot.builders.shop_flex_message.requests.head',
                   return_value=self._response(200, 'https://lh3.googleusercontent.com/ok.jpg')), \
             patch('line_bot.builders.shop_flex_message.config', return_value='fake_key'):
            result = FlexMessageBuilder.resolve_photo_url('old_ref', on_rejected=on_rejected)

        assert result == 'https://lh3.googleusercontent.com/ok.jpg'
        on_rejected.assert_not_called()

    def test_rejected_without_on_rejected_returns_default(self):
        """未提供 on_rejected 時，400/403 維持原行為回傳預設圖"""
        with patch('line_bot.builders.shop_flex_message.requests.head', return_value=self._response(403)) as mock_head, \
             patch('line_bot.builders.shop_flex_message.config', return_value='fake_key'):
            result = FlexMessageBuilder.resolve_photo_url('old_ref')

        assert result == FlexMessageBuilder.DEFAULT_PHOTO_URL
        assert mock_head.call_count == 1

    def test_returns_default_on_request_exception(self):
        """requests 拋出例外時，回傳預設圖"""
        import requests as req_lib

        with patch('line_bot.builders.shop_flex_message.requests.head', side_effect=req_lib.RequestException('timeout')), \
             patch('line_bot.builders.shop_flex_message.config', return_value='fake_key'):
            result = FlexMessageBuilder.resolve_photo_url('some_ref')

        assert result == FlexMessageBuilder.DEFAULT_PHOTO_URL


# FlexMessageBuilder._create_attribute_tags


class TestCreateAttributeTags:
    """測試 FlexMessageBuilder._create_attribute_tags"""

    def test_socket_yes_shows_tag(self):
        """has_socket='yes' 時顯示插座標籤"""
        tags = FlexMessageBuilder._create_attribute_tags({'has_socket': 'yes'})
        assert any('🔌 有插座' in t['text'] for t in tags)

    def test_socket_maybe_shows_tag(self):
        """has_socket='maybe' 時顯示插座標籤"""
        tags = FlexMessageBuilder._create_attribute_tags({'has_socket': 'maybe'})
        assert any('🔌 有插座' in t['text'] for t in tags)

    def test_socket_no_shows_no_tag(self):
        """has_socket='no' 時不顯示插座標籤"""
        tags = FlexMessageBuilder._create_attribute_tags({'has_socket': 'no'})
        assert not any('🔌' in t['text'] for t in tags)

    def test_limited_time_no_shows_unlimited_tag(self):
        """limited_time='no' 時顯示不限時標籤"""
        tags = FlexMessageBuilder._create_attribute_tags({'limited_time': 'no'})
        assert any('不限時' in t['text'] for t in tags)

    def test_limited_time_maybe_shows_conditional_tag(self):
        """limited_time='maybe' 時顯示視情況標籤"""
        tags = FlexMessageBuilder._create_attribute_tags({'limited_time': 'maybe'})
        assert any('視情況' in t['text'] for t in tags)

    def test_limited_time_yes_shows_limited_tag(self):
        """limited_time='yes' 時顯示有限時標籤"""
        tags = FlexMessageBuilder._create_attribute_tags({'limited_time': 'yes'})
        assert any('有限時' in t['text'] for t in tags)

    def test_no_attributes_returns_empty_list(self):
        """無 has_socket 和 limited_time 時，回傳空清單"""
        tags = FlexMessageBuilder._create_attribute_tags({})
        assert tags == []

    def test_both_attributes_return_two_tags(self):
        """同時有插座和限時資訊時，回傳兩個標籤"""
        tags = FlexMessageBuilder._create_attribute_tags({'has_socket': 'yes', 'limited_time': 'no'})
        assert len(tags) == 2

    def test_has_pet_yes_shows_tag(self):
        """has_pet='yes' 時顯示貓貓狗狗標籤"""
        tags = FlexMessageBuilder._create_attribute_tags({'has_pet': 'yes'})
        assert any('🐈' in t['text'] for t in tags)

    def test_has_pet_maybe_shows_tag(self):
        """has_pet='maybe' 時顯示貓貓狗狗標籤"""
        tags = FlexMessageBuilder._create_attribute_tags({'has_pet': 'maybe'})
        assert any('🐈' in t['text'] for t in tags)

    def test_has_pet_no_shows_no_tag(self):
        """has_pet='no' 時不顯示標籤"""
        tags = FlexMessageBuilder._create_attribute_tags({'has_pet': 'no'})
        assert not any('🐈' in t['text'] for t in tags)

    def test_pet_friendly_yes_shows_tag(self):
        """pet_friendly='yes' 時顯示寵物友善標籤"""
        tags = FlexMessageBuilder._create_attribute_tags({'pet_friendly': 'yes'})
        assert any('🐕' in t['text'] for t in tags)

    def test_pet_friendly_maybe_shows_tag(self):
        """pet_friendly='maybe' 時顯示寵物友善標籤"""
        tags = FlexMessageBuilder._create_attribute_tags({'pet_friendly': 'maybe'})
        assert any('🐕' in t['text'] for t in tags)

    def test_pet_friendly_no_shows_no_tag(self):
        """pet_friendly='no' 時不顯示標籤"""
        tags = FlexMessageBuilder._create_attribute_tags({'pet_friendly': 'no'})
        assert not any('🐕' in t['text'] for t in tags)

    def test_all_pet_attributes_return_tags(self):
        """has_pet 和 pet_friendly 同時為 yes 時，各回傳一個標籤"""
        tags = FlexMessageBuilder._create_attribute_tags({'has_pet': 'yes', 'pet_friendly': 'yes'})
        assert any('🐈' in t['text'] for t in tags)
        assert any('🐕' in t['text'] for t in tags)


# FlexMessageBuilder._create_tag_element


class TestCreateTagElement:
    """測試 FlexMessageBuilder._create_tag_element"""

    def test_socket_tag_has_correct_color(self):
        """socket 類型的標籤使用正確顏色"""
        element = FlexMessageBuilder._create_tag_element('🔌 有插座', 'socket')
        assert element['color'] == '#0F5132'
        assert element['backgroundColor'] == '#D1E7DD'

    def test_limited_time_tag_has_correct_color(self):
        """limited_time 類型的標籤使用正確顏色"""
        element = FlexMessageBuilder._create_tag_element('⏱ 不限時', 'limited_time')
        assert element['color'] == '#055160'
        assert element['backgroundColor'] == '#CFF4FC'

    def test_tag_element_required_fields(self):
        """標籤元素包含所有必要欄位"""
        element = FlexMessageBuilder._create_tag_element('測試', 'socket')
        assert element['type'] == 'text'
        assert element['text'] == '測試'
        assert element['size'] == 'xs'
        assert element['cornerRadius'] == '12px'
        assert element['flex'] == 0

    def test_unknown_tag_type_uses_default_colors(self):
        """未知類型使用預設顏色"""
        element = FlexMessageBuilder._create_tag_element('?', 'unknown')
        assert element['color'] == '#666666'
        assert element['backgroundColor'] == '#EEEEEE'


# FlexMessageBuilder._create_tags_box


class TestCreateTagsBox:
    """測試 FlexMessageBuilder._create_tags_box"""

    def test_creates_horizontal_box(self):
        """1 個 tag 時回傳 horizontal layout 的 box"""
        tags = [{'type': 'text', 'text': 'tag1'}]
        box = FlexMessageBuilder._create_tags_box(tags)
        assert box['type'] == 'box'
        assert box['layout'] == 'horizontal'
        assert box['contents'] == tags

    def test_two_tags_creates_horizontal_box(self):
        """2 個 tag 時維持 horizontal layout 單列"""
        tags = [{'type': 'text', 'text': 'tag1'}, {'type': 'text', 'text': 'tag2'}]
        box = FlexMessageBuilder._create_tags_box(tags)
        assert box['layout'] == 'horizontal'
        assert box['contents'] == tags

    def test_three_tags_creates_vertical_box_with_two_rows(self):
        """3 個 tag 時回傳 vertical box，第一列 2 個、第二列 1 個"""
        tags = [{'type': 'text', 'text': f'tag{i}'} for i in range(3)]
        box = FlexMessageBuilder._create_tags_box(tags)
        assert box['type'] == 'box'
        assert box['layout'] == 'vertical'
        assert len(box['contents']) == 2
        assert box['contents'][0]['layout'] == 'horizontal'
        assert len(box['contents'][0]['contents']) == 2
        assert box['contents'][1]['layout'] == 'horizontal'
        assert len(box['contents'][1]['contents']) == 1

    def test_four_tags_creates_vertical_box_with_two_rows(self):
        """4 個 tag 時回傳 vertical box，兩列各 2 個"""
        tags = [{'type': 'text', 'text': f'tag{i}'} for i in range(4)]
        box = FlexMessageBuilder._create_tags_box(tags)
        assert box['type'] == 'box'
        assert box['layout'] == 'vertical'
        assert len(box['contents']) == 2
        assert len(box['contents'][0]['contents']) == 2
        assert len(box['contents'][1]['contents']) == 2


# FlexMessageBuilder.format_opening_hours


class TestFormatOpeningHours:
    """測試 FlexMessageBuilder.format_opening_hours"""

    def test_returns_prompt_when_empty(self):
        """空輸入回傳『營業時間未提供』"""
        assert FlexMessageBuilder.format_opening_hours(None) == '營業時間未提供'
        assert FlexMessageBuilder.format_opening_hours({}) == '營業時間未提供'
        assert FlexMessageBuilder.format_opening_hours([]) == '營業時間未提供'

    def test_handles_dict_format_returns_todays_hours(self):
        """dict 格式正確回傳今日營業時間"""
        # 星期一 = isoweekday 1，index 0
        hours_dict = {'星期一': '09:00 – 21:00', '星期二': '10:00 – 22:00'}
        with patch('line_bot.builders.shop_flex_message.date') as mock_date:
            mock_date.today.return_value.isoweekday.return_value = 1
            result = FlexMessageBuilder.format_opening_hours(hours_dict)
        assert result == '09:00 – 21:00'

    def test_handles_list_format(self):
        """list 格式（Google API 格式）正確解析並回傳今日營業時間"""
        hours_list = ['星期三: 08:00 – 20:00', '星期四: 09:00 – 21:00']
        with patch('line_bot.builders.shop_flex_message.date') as mock_date:
            mock_date.today.return_value.isoweekday.return_value = 3  # 星期三
            result = FlexMessageBuilder.format_opening_hours(hours_list)
        assert result == '08:00 – 20:00'

    def test_returns_closed_when_day_is_rest(self):
        """當天標記為休息時，回傳『今日休息』"""
        hours_dict = {'星期五': '休息'}
        with patch('line_bot.builders.shop_flex_message.date') as mock_date:
            mock_date.today.return_value.isoweekday.return_value = 5  # 星期五
            result = FlexMessageBuilder.format_opening_hours(hours_dict)
        assert result == '今日休息'

    def test_returns_closed_for_public_holiday_text(self):
        """公休文字也回傳『今日休息』"""
        hours_dict = {'星期六': '公休'}
        with patch('line_bot.builders.shop_flex_message.date') as mock_date:
            mock_date.today.return_value.isoweekday.return_value = 6  # 星期六
            result = FlexMessageBuilder.format_opening_hours(hours_dict)
        assert result == '今日休息'

    def test_returns_no_operation_when_day_missing(self):
        """今日不在資料中時，回傳『今日未營業』"""
        hours_dict = {'星期一': '09:00 – 21:00'}
        with patch('line_bot.builders.shop_flex_message.date') as mock_date:
            mock_date.today.return_value.isoweekday.return_value = 2  # 星期二（不在 dict 中）
            result = FlexMessageBuilder.format_opening_hours(hours_dict)
        assert result == '今日未營業'


# FlexMessageBuilder.create_shop_flex_message


class TestCreateShopFlexMessage:
    """測試 FlexMessageBuilder.create_shop_flex_message"""

    def _make_info(self, **kwargs):
        defaults = {
            'place_id': 'test_place_id',
            'name': '測試咖啡店',
            'address': '台北市信義區',
            'phone': '02-1234-5678',
            'rating': 4.5,
            'user_ratings_total': 100,
            'google_maps': 'https://maps.google.com/?q=test',
            'website': 'https://example.com',
            'opening_hours': {'星期一': '09:00 – 21:00'},
            'photo_s3_url': 'https://s3.example.com/photo.jpg',
            'photo_reference': '',
            'has_socket': None,
            'limited_time': None,
        }
        defaults.update(kwargs)
        return defaults

    def test_returns_bubble_type(self):
        """回傳的 dict 型別為 bubble"""
        info = self._make_info()
        result = FlexMessageBuilder.create_shop_flex_message(info)
        assert result['type'] == 'bubble'

    def test_hero_image_uses_photo_url(self):
        """hero image 使用 get_photo_url 取得的 URL"""
        info = self._make_info(photo_s3_url='https://s3.example.com/photo.jpg')
        result = FlexMessageBuilder.create_shop_flex_message(info)
        assert result['hero']['url'] == 'https://s3.example.com/photo.jpg'

    def test_hero_image_aspect_ratio(self):
        """hero image 使用 20:13 的比例"""
        result = FlexMessageBuilder.create_shop_flex_message(self._make_info())
        assert result['hero']['aspectRatio'] == '20:13'
        assert result['hero']['aspectMode'] == 'cover'

    def test_shop_name_in_body(self):
        """店名出現在 body contents 中"""
        info = self._make_info(name='星巴克信義門市')
        result = FlexMessageBuilder.create_shop_flex_message(info)
        body_contents = result['body']['contents']
        name_element = body_contents[0]
        assert name_element['text'] == '星巴克信義門市'

    def test_single_result_footer_has_map_and_website(self):
        """單筆結果 (is_multiple=False)：footer 有地圖和網站按鈕"""
        info = self._make_info(website='https://starbucks.com.tw')
        result = FlexMessageBuilder.create_shop_flex_message(info, is_multiple=False)
        footer_actions = [btn['action']['label'] for btn in result['footer']['contents']]
        assert '看地圖' in footer_actions
        assert '網站' in footer_actions

    def test_single_result_footer_no_website_only_map(self):
        """單筆結果且無官方網站時，footer 只有地圖按鈕"""
        info = self._make_info(website=None)
        result = FlexMessageBuilder.create_shop_flex_message(info, is_multiple=False)
        footer_labels = [btn['action']['label'] for btn in result['footer']['contents']]
        assert '看地圖' in footer_labels
        assert '網站' not in footer_labels

    def test_single_result_footer_no_website_string(self):
        """website 為 '無提供' 字串時，不顯示網站按鈕"""
        info = self._make_info(website='無提供')
        result = FlexMessageBuilder.create_shop_flex_message(info, is_multiple=False)
        footer_labels = [btn['action']['label'] for btn in result['footer']['contents']]
        assert '網站' not in footer_labels

    def test_multiple_results_footer_has_map_and_select(self):
        """多筆結果 (is_multiple=True)：footer 有地圖和選擇這間按鈕"""
        info = self._make_info()
        result = FlexMessageBuilder.create_shop_flex_message(info, is_multiple=True)
        footer_labels = [btn['action']['label'] for btn in result['footer']['contents']]
        assert '看地圖 ' in footer_labels
        assert '選擇這間' in footer_labels

    def test_multiple_results_select_button_data(self):
        """多筆結果的選擇按鈕 postback data 格式正確"""
        info = self._make_info(place_id='abc123')
        result = FlexMessageBuilder.create_shop_flex_message(info, is_multiple=True)
        select_btn = next(b for b in result['footer']['contents'] if b['action'].get('label') == '選擇這間')
        assert select_btn['action']['data'] == 'action=view_detail&place_id=abc123'

    def test_inserts_tags_box_when_attributes_present(self):
        """有插座/限時屬性時，tags_box 插入 body contents 的第三個位置"""
        info = self._make_info(has_socket='yes', limited_time='no')
        result = FlexMessageBuilder.create_shop_flex_message(info)
        body_contents = result['body']['contents']
        # index 0: 店名, index 1: 評分, index 2: tags_box
        tags_box = body_contents[2]
        assert tags_box['type'] == 'box'
        assert tags_box['layout'] == 'horizontal'

    def test_no_tags_box_when_no_attributes(self):
        """無插座/限時屬性時，body 不插入 tags_box"""
        info = self._make_info(has_socket=None, limited_time=None)
        result = FlexMessageBuilder.create_shop_flex_message(info)
        body_contents = result['body']['contents']
        # index 0: 店名, index 1: 評分, index 2: 詳細資訊 box (不是 tags_box)
        detail_box = body_contents[2]
        assert detail_box['layout'] == 'vertical'

    def test_rating_stars_five_full(self):
        """評分 5.0 生成 5 顆滿星"""
        info = self._make_info(rating=5.0)
        result = FlexMessageBuilder.create_shop_flex_message(info)
        rating_box = result['body']['contents'][1]
        star_icons = [c for c in rating_box['contents'] if c['type'] == 'icon']
        assert len(star_icons) == 5
        gold_url = 'https://developers-resource.landpress.line.me/fx/img/review_gold_star_28.png'
        assert all(s['url'] == gold_url for s in star_icons)

    def test_rating_stars_with_gray(self):
        """低評分包含灰星"""
        info = self._make_info(rating=3.0)
        result = FlexMessageBuilder.create_shop_flex_message(info)
        rating_box = result['body']['contents'][1]
        star_icons = [c for c in rating_box['contents'] if c['type'] == 'icon']
        gray_url = 'https://developers-resource.landpress.line.me/fx/img/review_gray_star_28.png'
        gray_stars = [s for s in star_icons if s['url'] == gray_url]
        assert len(gray_stars) == 2

    def test_rating_text_with_review_count(self):
        """評分文字包含評論數"""
        info = self._make_info(rating=4.5, user_ratings_total=200)
        result = FlexMessageBuilder.create_shop_flex_message(info)
        rating_box = result['body']['contents'][1]
        rating_text_element = next(c for c in rating_box['contents'] if c['type'] == 'text')
        assert '200則評論' in rating_text_element['text']

    def test_no_rating_generates_no_stars(self):
        """無評分時不生成星星圖示"""
        info = self._make_info(rating=None)
        result = FlexMessageBuilder.create_shop_flex_message(info)
        rating_box = result['body']['contents'][1]
        star_icons = [c for c in rating_box['contents'] if c['type'] == 'icon']
        assert star_icons == []

    def test_multiple_results_calls_get_photo_url_with_sync_resolve_disallowed(self):
        """is_multiple=True 時，get_photo_url 被呼叫時帶入 allow_sync_resolve=False"""
        info = self._make_info()
        with patch.object(FlexMessageBuilder, 'get_photo_url', return_value=FlexMessageBuilder.DEFAULT_PHOTO_URL) as mock_get_photo_url:
            FlexMessageBuilder.create_shop_flex_message(info, is_multiple=True)

        mock_get_photo_url.assert_called_once_with(info, allow_sync_resolve=False)

    def test_single_result_calls_get_photo_url_with_sync_resolve_allowed(self):
        """is_multiple=False（或不傳，預設值）時，get_photo_url 被呼叫時帶入 allow_sync_resolve=True"""
        info = self._make_info()
        with patch.object(FlexMessageBuilder, 'get_photo_url', return_value=FlexMessageBuilder.DEFAULT_PHOTO_URL) as mock_get_photo_url:
            FlexMessageBuilder.create_shop_flex_message(info)

        mock_get_photo_url.assert_called_once_with(info, allow_sync_resolve=True)

    def test_photo_url_override_used_directly_without_calling_get_photo_url(self):
        """photo_url_override 有值時，直接用它當 photo_url，不呼叫 get_photo_url"""
        info = self._make_info()
        with patch.object(FlexMessageBuilder, 'get_photo_url') as mock_get_photo_url:
            result = FlexMessageBuilder.create_shop_flex_message(
                info, is_multiple=True, photo_url_override='https://example.com/x.jpg'
            )

        mock_get_photo_url.assert_not_called()
        assert result['hero']['url'] == 'https://example.com/x.jpg'

    def test_photo_url_override_none_falls_back_to_get_photo_url(self):
        """photo_url_override 為 None（顯式傳入或不傳）時，行為與現行一致，仍呼叫 get_photo_url"""
        info = self._make_info()
        with patch.object(FlexMessageBuilder, 'get_photo_url', return_value=FlexMessageBuilder.DEFAULT_PHOTO_URL) as mock_get_photo_url:
            FlexMessageBuilder.create_shop_flex_message(info, is_multiple=True, photo_url_override=None)

        mock_get_photo_url.assert_called_once_with(info, allow_sync_resolve=False)


class TestShopFlexMessageAiSummary:
    """測試 create_shop_flex_message 的 AI 評論摘要區塊（見 openspec/changes/ai-summary-inline-display）"""

    SUMMARY = '肉桂捲與手沖美式是招牌，空間安靜有插座，適合一個人工作或看書。'

    def _make_info(self, **kwargs):
        return TestCreateShopFlexMessage()._make_info(**kwargs)

    def _build(self, is_multiple=False, **kwargs):
        info = self._make_info(**kwargs)
        return FlexMessageBuilder.create_shop_flex_message(
            info, is_multiple=is_multiple, photo_url_override='https://example.com/x.jpg'
        )

    @staticmethod
    def _find_summary_box(bubble):
        for index, element in enumerate(bubble['body']['contents']):
            if element.get('type') != 'box':
                continue
            texts = [c.get('text') for c in element.get('contents', []) if c.get('type') == 'text']
            if '🤖 評論摘要' in texts:
                return index, element
        return None, None

    @staticmethod
    def _summary_text(box):
        return next(c for c in box['contents'] if c.get('type') == 'text' and c['text'] != '🤖 評論摘要')

    @staticmethod
    def _has_separator(bubble):
        return any(e.get('type') == 'separator' for e in bubble['body']['contents'])

    def test_single_shows_summary_after_detail_box(self):
        """單筆：摘要區塊位於營業時間所在的詳細資訊 box 之後，前面有 separator"""
        bubble = self._build(ai_summary=self.SUMMARY)
        contents = bubble['body']['contents']

        index, box = self._find_summary_box(bubble)

        assert box is not None
        assert self._summary_text(box)['text'] == self.SUMMARY
        assert contents[index - 1]['type'] == 'separator'
        detail_index = next(
            i for i, e in enumerate(contents)
            if e.get('type') == 'box' and any(
                c.get('type') == 'box' and any(t.get('text') == '⏰ 營業' for t in c.get('contents', []))
                for c in e.get('contents', [])
            )
        )
        assert detail_index < index - 1
        assert index == len(contents) - 1

    @pytest.mark.parametrize('is_multiple', [False, True])
    def test_summary_style_is_small_muted_and_italic(self, is_multiple):
        """單筆與多筆：摘要文字為 xs 灰色斜體、可換行（商業邏輯變更：由行數截斷改為完整呈現並改用斜體，見 spec「卡片完整顯示 AI 評論摘要」）"""
        _, box = self._find_summary_box(self._build(is_multiple=is_multiple, ai_summary=self.SUMMARY))
        text = self._summary_text(box)

        assert text['text'] == self.SUMMARY
        assert text['size'] == 'xs'
        assert text['color'] == '#999999'
        assert text['style'] == 'italic'
        assert text['wrap'] is True

    @pytest.mark.parametrize('is_multiple', [False, True])
    def test_summary_is_not_line_truncated(self, is_multiple):
        """單筆與多筆：摘要不設 maxLines，內容完整呈現"""
        _, box = self._find_summary_box(self._build(is_multiple=is_multiple, ai_summary=self.SUMMARY))

        assert 'maxLines' not in self._summary_text(box)

    def test_old_100_char_summary_is_shown_in_full(self):
        """舊版約 100 字的摘要完整顯示，不被截斷"""
        old_summary = '咖' * 100

        _, box = self._find_summary_box(self._build(is_multiple=True, ai_summary=old_summary))

        assert self._summary_text(box)['text'] == old_summary

    @pytest.mark.parametrize('is_multiple', [False, True])
    def test_whitespace_between_detail_and_summary(self, is_multiple):
        """店家資訊與摘要之間留白：separator 上方 xxl、摘要 box 上方 lg，大於詳細資訊 box 的 lg 間距"""
        bubble = self._build(is_multiple=is_multiple, ai_summary=self.SUMMARY)
        index, box = self._find_summary_box(bubble)
        separator = bubble['body']['contents'][index - 1]

        assert separator['margin'] == 'xxl'
        assert box['margin'] == 'lg'

    def test_summary_is_stripped(self):
        """摘要前後空白與換行會被去除"""
        _, box = self._find_summary_box(self._build(ai_summary=f'\n  {self.SUMMARY}  \n'))

        assert self._summary_text(box)['text'] == self.SUMMARY

    @pytest.mark.parametrize('is_multiple', [False, True])
    @pytest.mark.parametrize('summary', [None, '', '   ', '\n\t\n'])
    def test_no_summary_block_when_blank(self, is_multiple, summary):
        """摘要為 None、空字串、純空白時，不顯示標題、分隔線與任何 placeholder"""
        bubble = self._build(is_multiple=is_multiple, ai_summary=summary)

        _, box = self._find_summary_box(bubble)

        assert box is None
        assert not self._has_separator(bubble)

    @pytest.mark.parametrize('is_multiple', [False, True])
    def test_no_summary_block_when_key_missing(self, is_multiple):
        """info 沒有 ai_summary key（例如舊資料或非 DB 來源）時，不顯示摘要區塊"""
        info = self._make_info()
        info.pop('ai_summary', None)

        bubble = FlexMessageBuilder.create_shop_flex_message(
            info, is_multiple=is_multiple, photo_url_override='https://example.com/x.jpg'
        )

        assert self._find_summary_box(bubble) == (None, None)
        assert not self._has_separator(bubble)

    def test_non_string_summary_is_ignored(self):
        """ai_summary 型別錯誤（非字串）時不顯示，也不拋例外"""
        bubble = self._build(ai_summary=123)

        assert self._find_summary_box(bubble) == (None, None)

    @pytest.mark.parametrize('is_multiple', [False, True])
    def test_overlong_summary_is_capped_in_payload(self, is_multiple):
        """模型不守字數時，送進 Flex JSON 的摘要仍有字數上限並以省略號結尾，避免 carousel 超過 LINE payload 上限"""
        limit = FlexMessageBuilder.AI_SUMMARY_MAX_CHARS
        _, box = self._find_summary_box(self._build(is_multiple=is_multiple, ai_summary='肉' * (limit * 10)))

        text = self._summary_text(box)['text']
        assert len(text) == limit + 1
        assert text.endswith('…')

    def test_summary_at_char_limit_is_not_truncated(self):
        """剛好等於字數上限時不截斷、不加省略號"""
        summary = '肉' * FlexMessageBuilder.AI_SUMMARY_MAX_CHARS

        _, box = self._find_summary_box(self._build(ai_summary=summary))

        assert self._summary_text(box)['text'] == summary

    def test_char_limit_leaves_room_for_old_100_char_summaries(self):
        """字數上限需大於舊版 100 字摘要，舊資料不會被字數上限截斷"""
        assert FlexMessageBuilder.AI_SUMMARY_MAX_CHARS >= 100

    def test_single_footer_and_tags_unchanged_with_summary(self):
        """有摘要時，單筆 footer 按鈕順序與屬性標籤位置不變"""
        bubble = self._build(ai_summary=self.SUMMARY, has_socket='yes', limited_time='no')

        footer_labels = [btn['action']['label'] for btn in bubble['footer']['contents']]
        assert footer_labels == ['看地圖', '打電話', '網站']
        assert bubble['body']['contents'][2]['layout'] == 'horizontal'

    def test_multiple_footer_unchanged_with_summary(self):
        """有摘要時，多筆 footer 仍為「看地圖」「選擇這間」"""
        bubble = self._build(is_multiple=True, ai_summary=self.SUMMARY)

        footer_labels = [btn['action']['label'] for btn in bubble['footer']['contents']]
        assert footer_labels == ['看地圖 ', '選擇這間']


class TestBuildTelUri:
    """測試 FlexMessageBuilder._build_tel_uri"""

    @pytest.mark.parametrize('phone, expected', [
        ('02 2345 6789', 'tel:0223456789'),
        ('02-2345-6789', 'tel:0223456789'),
        ('(02) 2345-6789', 'tel:0223456789'),
        ('0912 345 678', 'tel:0912345678'),
        ('+886 2 2345 6789', 'tel:+886223456789'),
        ('  02 2345 6789  ', 'tel:0223456789'),
    ])
    def test_strips_separators(self, phone, expected):
        """移除空白、連字號、括號，保留開頭 +"""
        assert FlexMessageBuilder._build_tel_uri(phone) == expected

    @pytest.mark.parametrize('phone', [
        '02-2345-6789 #123',
        '02-2345-6789#123',
        '02-2345-6789 分機 123',
        '02-2345-6789 ext. 123',
        '02-2345-6789 EXT 123',
        '02-2345-6789 轉 123',
        '02-2345-6789, 123',
        '02-2345-6789;123',
    ])
    def test_truncates_extension(self, phone):
        """分機標記之後的內容不併入號碼"""
        assert FlexMessageBuilder._build_tel_uri(phone) == 'tel:0223456789'

    def test_full_width_digits(self):
        """全形數字與符號轉半形"""
        assert FlexMessageBuilder._build_tel_uri('０２－２３４５－６７８９') == 'tel:0223456789'

    def test_plus_only_kept_at_start(self):
        """非開頭的 + 視為分隔符號移除"""
        assert FlexMessageBuilder._build_tel_uri('02+2345+6789') == 'tel:0223456789'

    @pytest.mark.parametrize('phone', ['無提供', '未提供電話', '電話未提供', '', '   ', '---', '+'])
    def test_placeholder_or_no_digits_returns_none(self, phone):
        """佔位字串或不含數字時回傳 None"""
        assert FlexMessageBuilder._build_tel_uri(phone) is None

    @pytest.mark.parametrize('phone', [None, 223456789, 2.5, ['02 2345 6789'], {'phone': '02'}])
    def test_non_string_returns_none(self, phone):
        """非字串輸入回傳 None"""
        assert FlexMessageBuilder._build_tel_uri(phone) is None

    def test_min_length_boundary(self):
        """3 位數字為下限（含），2 位不合法"""
        assert FlexMessageBuilder._build_tel_uri('110') == 'tel:110'
        assert FlexMessageBuilder._build_tel_uri('11') is None

    def test_max_length_boundary(self):
        """15 位數字為上限（含），16 位不合法"""
        assert FlexMessageBuilder._build_tel_uri('1' * 15) == f'tel:{"1" * 15}'
        assert FlexMessageBuilder._build_tel_uri('1' * 16) is None
        assert FlexMessageBuilder._build_tel_uri('+' + '1' * 16) is None

    def test_extension_only_returns_none(self):
        """只有分機標記、前面無號碼時回傳 None"""
        assert FlexMessageBuilder._build_tel_uri('#123') is None


class TestPhoneCallButton:
    """測試單筆詳細卡片 footer 的「打電話」按鈕"""

    def _make_info(self, **kwargs):
        defaults = {
            'place_id': 'test_place_id',
            'name': '測試咖啡店',
            'address': '台北市信義區',
            'phone': '02 2345 6789',
            'rating': 4.5,
            'user_ratings_total': 100,
            'google_maps': 'https://maps.google.com/?q=test',
            'website': 'https://example.com',
            'opening_hours': {'星期一': '09:00 – 21:00'},
            'photo_s3_url': 'https://s3.example.com/photo.jpg',
            'photo_reference': '',
            'has_socket': None,
            'limited_time': None,
        }
        defaults.update(kwargs)
        return defaults

    def _footer_labels(self, result):
        return [btn['action']['label'] for btn in result['footer']['contents']]

    def test_single_result_has_call_button_with_tel_uri(self):
        """單筆且電話合法：footer 有打電話按鈕，action 為 tel URI"""
        result = FlexMessageBuilder.create_shop_flex_message(self._make_info(), is_multiple=False)
        call_btn = next(b for b in result['footer']['contents'] if b['action']['label'] == '打電話')
        assert call_btn['type'] == 'button'
        assert call_btn['action']['type'] == 'uri'
        assert call_btn['action']['uri'] == 'tel:0223456789'

    def test_button_order_map_call_website(self):
        """按鈕順序為看地圖、打電話、網站"""
        result = FlexMessageBuilder.create_shop_flex_message(self._make_info(), is_multiple=False)
        assert self._footer_labels(result) == ['看地圖', '打電話', '網站']

    def test_button_order_without_website(self):
        """無官方網站時為看地圖、打電話"""
        result = FlexMessageBuilder.create_shop_flex_message(self._make_info(website='無提供'), is_multiple=False)
        assert self._footer_labels(result) == ['看地圖', '打電話']

    @pytest.mark.parametrize('phone', [None, '', '無提供', '未提供電話'])
    def test_no_call_button_when_phone_invalid(self, phone):
        """電話缺失或為佔位字串時不顯示打電話按鈕"""
        result = FlexMessageBuilder.create_shop_flex_message(self._make_info(phone=phone), is_multiple=False)
        assert '打電話' not in self._footer_labels(result)

    def test_no_call_button_when_phone_key_missing(self):
        """info 沒有 phone key 時不顯示打電話按鈕"""
        info = self._make_info()
        del info['phone']
        result = FlexMessageBuilder.create_shop_flex_message(info, is_multiple=False)
        assert '打電話' not in self._footer_labels(result)

    def test_multiple_results_no_call_button(self):
        """多筆結果卡片不顯示打電話按鈕"""
        result = FlexMessageBuilder.create_shop_flex_message(self._make_info(), is_multiple=True)
        assert '打電話' not in self._footer_labels(result)
