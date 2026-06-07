import pytest
from unittest.mock import MagicMock, patch

from linebot.v3.messaging import (
    QuickReply,
    LocationAction,
)

from line_bot.builders.flex_builder import (
    FlexMessageBuilder,
    PostbackBuilder,
    QuickReplyBuilder,
)
from line_bot.constants import MenuAction
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

        mock_resolve.assert_called_once_with('ref123')
        mock_upload.assert_called_once_with('p1')
        assert result == resolved

    def test_does_not_trigger_upload_when_resolved_to_default(self):
        """解析後得到預設圖時，不觸發 S3 上傳"""
        info = {'photo_s3_url': '', 'photo_reference': 'ref123', 'place_id': 'p1'}

        with patch.object(FlexMessageBuilder, 'resolve_photo_url', return_value=FlexMessageBuilder.DEFAULT_PHOTO_URL), \
             patch.object(FlexMessageBuilder, '_trigger_s3_upload') as mock_upload:
            FlexMessageBuilder.get_photo_url(info)

        mock_upload.assert_not_called()

    def test_returns_default_when_no_photo_reference_or_s3(self):
        """photo_s3_url 和 photo_reference 皆為空時，回傳預設圖"""
        info = {'photo_s3_url': '', 'photo_reference': '', 'place_id': 'p1'}
        result = FlexMessageBuilder.get_photo_url(info)
        assert result == FlexMessageBuilder.DEFAULT_PHOTO_URL

    @pytest.mark.django_db
    def test_accepts_cafe_model_object(self):
        """傳入 Cafe 物件時，轉換為 dict 處理"""
        cafe = CafeFactory(photo_s3_url='https://s3.example.com/cafe.jpg')
        result = FlexMessageBuilder.get_photo_url(cafe)
        assert result == 'https://s3.example.com/cafe.jpg'



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

        with patch('line_bot.builders.flex_builder.requests.head', return_value=mock_response), \
             patch('line_bot.builders.flex_builder.config', return_value='fake_key'):
            result = FlexMessageBuilder.resolve_photo_url('valid_ref')

        assert result == 'https://lh3.googleusercontent.com/photo.jpg'

    def test_returns_default_when_status_not_200(self):
        """HTTP 狀態非 200 時，回傳預設圖"""
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch('line_bot.builders.flex_builder.requests.head', return_value=mock_response), \
             patch('line_bot.builders.flex_builder.config', return_value='fake_key'):
            result = FlexMessageBuilder.resolve_photo_url('some_ref')

        assert result == FlexMessageBuilder.DEFAULT_PHOTO_URL

    def test_returns_default_on_request_exception(self):
        """requests 拋出例外時，回傳預設圖"""
        import requests as req_lib

        with patch('line_bot.builders.flex_builder.requests.head', side_effect=req_lib.RequestException('timeout')), \
             patch('line_bot.builders.flex_builder.config', return_value='fake_key'):
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
        """回傳 horizontal layout 的 box"""
        tags = [{'type': 'text', 'text': 'tag1'}]
        box = FlexMessageBuilder._create_tags_box(tags)
        assert box['type'] == 'box'
        assert box['layout'] == 'horizontal'
        assert box['contents'] == tags



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
        with patch('line_bot.builders.flex_builder.date') as mock_date:
            mock_date.today.return_value.isoweekday.return_value = 1
            result = FlexMessageBuilder.format_opening_hours(hours_dict)
        assert result == '09:00 – 21:00'

    def test_handles_list_format(self):
        """list 格式（Google API 格式）正確解析並回傳今日營業時間"""
        hours_list = ['星期三: 08:00 – 20:00', '星期四: 09:00 – 21:00']
        with patch('line_bot.builders.flex_builder.date') as mock_date:
            mock_date.today.return_value.isoweekday.return_value = 3  # 星期三
            result = FlexMessageBuilder.format_opening_hours(hours_list)
        assert result == '08:00 – 20:00'

    def test_returns_closed_when_day_is_rest(self):
        """當天標記為休息時，回傳『今日休息』"""
        hours_dict = {'星期五': '休息'}
        with patch('line_bot.builders.flex_builder.date') as mock_date:
            mock_date.today.return_value.isoweekday.return_value = 5  # 星期五
            result = FlexMessageBuilder.format_opening_hours(hours_dict)
        assert result == '今日休息'

    def test_returns_closed_for_public_holiday_text(self):
        """公休文字也回傳『今日休息』"""
        hours_dict = {'星期六': '公休'}
        with patch('line_bot.builders.flex_builder.date') as mock_date:
            mock_date.today.return_value.isoweekday.return_value = 6  # 星期六
            result = FlexMessageBuilder.format_opening_hours(hours_dict)
        assert result == '今日休息'

    def test_returns_no_operation_when_day_missing(self):
        """今日不在資料中時，回傳『今日未營業』"""
        hours_dict = {'星期一': '09:00 – 21:00'}
        with patch('line_bot.builders.flex_builder.date') as mock_date:
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
        """單筆結果 (is_multiple=False)：footer 有地圖和官方網站按鈕"""
        info = self._make_info(website='https://starbucks.com.tw')
        result = FlexMessageBuilder.create_shop_flex_message(info, is_multiple=False)
        footer_actions = [btn['action']['label'] for btn in result['footer']['contents']]
        assert '看地圖' in footer_actions
        assert '官方網站' in footer_actions

    def test_single_result_footer_no_website_only_map(self):
        """單筆結果且無官方網站時，footer 只有地圖按鈕"""
        info = self._make_info(website=None)
        result = FlexMessageBuilder.create_shop_flex_message(info, is_multiple=False)
        footer_labels = [btn['action']['label'] for btn in result['footer']['contents']]
        assert '看地圖' in footer_labels
        assert '官方網站' not in footer_labels

    def test_single_result_footer_no_website_string(self):
        """website 為 '無提供' 字串時，不顯示官方網站按鈕"""
        info = self._make_info(website='無提供')
        result = FlexMessageBuilder.create_shop_flex_message(info, is_multiple=False)
        footer_labels = [btn['action']['label'] for btn in result['footer']['contents']]
        assert '官方網站' not in footer_labels

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


# PostbackBuilder.create_cafe_action_postback


class TestPostbackBuilderCreateCafeActionPostback:
    """測試 PostbackBuilder.create_cafe_action_postback"""

    def _make_info(self, place_id='test_place_id'):
        return {'place_id': place_id}

    def test_not_favorited_shows_star_label(self):
        """未收藏時，收藏按鈕顯示 '⭐ 收藏'"""
        result = PostbackBuilder.create_cafe_action_postback(self._make_info(), is_favorited=False)
        actions = result.to_dict()['template']['actions']
        fav_action = actions[0]
        assert fav_action['label'] == '⭐ 收藏'
        assert 'action=favorite' in fav_action['data']

    def test_favorited_shows_remove_label(self):
        """已收藏時，收藏按鈕顯示 '💔 取消收藏'"""
        result = PostbackBuilder.create_cafe_action_postback(self._make_info(), is_favorited=True)
        actions = result.to_dict()['template']['actions']
        fav_action = actions[0]
        assert fav_action['label'] == '💔 取消收藏'
        assert 'action=unfavorite' in fav_action['data']

    def test_postback_data_contains_place_id(self):
        """postback data 包含正確的 place_id"""
        result = PostbackBuilder.create_cafe_action_postback({'place_id': 'abc_xyz'})
        actions = result.to_dict()['template']['actions']
        for action in actions:
            assert 'place_id=abc_xyz' in action['data']

    def test_contains_four_actions(self):
        """按鈕選單包含 4 個 action（收藏、分享、評價、問 AI）"""
        result = PostbackBuilder.create_cafe_action_postback(self._make_info())
        actions = result.to_dict()['template']['actions']
        assert len(actions) == 4

    def test_all_action_labels_present(self):
        """按鈕選單包含所有預期的標籤"""
        result = PostbackBuilder.create_cafe_action_postback(self._make_info())
        labels = [a['label'] for a in result.to_dict()['template']['actions']]
        assert '⭐ 收藏' in labels
        assert '🔗 分享' in labels
        assert '⭐ 評價' in labels
        assert '🤖 看看AI的怎麼說' in labels



# QuickReplyBuilder


class TestQuickReplyBuilderCreateSearchAgainActions:
    """測試 QuickReplyBuilder.create_search_again_actions"""

    def test_returns_quick_reply_with_three_items(self):
        """回傳 QuickReply 包含 3 個選項"""
        result = QuickReplyBuilder.create_search_again_actions()
        assert isinstance(result, QuickReply)
        assert len(result.items) == 3

    def test_contains_search_shop_name_action(self):
        """包含『再找一間』選項"""
        result = QuickReplyBuilder.create_search_again_actions()
        datas = [item.action.data for item in result.items]
        assert any(MenuAction.SEARCH_SHOP_NAME in d for d in datas)

    def test_contains_share_location_action(self):
        """包含『附近搜尋』選項"""
        result = QuickReplyBuilder.create_search_again_actions()
        datas = [item.action.data for item in result.items]
        assert any(MenuAction.SHARE_LOCATION in d for d in datas)

    def test_contains_favorites_action(self):
        """包含『我的收藏』選項"""
        result = QuickReplyBuilder.create_search_again_actions()
        datas = [item.action.data for item in result.items]
        assert any(MenuAction.FAVORITES in d for d in datas)


class TestQuickReplyBuilderCreateCarouselPaginationActions:
    """測試 QuickReplyBuilder.create_carousel_pagination_actions"""

    def test_returns_quick_reply_with_four_items(self):
        """回傳 QuickReply 包含 4 個選項"""
        result = QuickReplyBuilder.create_carousel_pagination_actions()
        assert isinstance(result, QuickReply)
        assert len(result.items) == 4

    def test_contains_search_address_action(self):
        """包含路名查詢選項"""
        result = QuickReplyBuilder.create_carousel_pagination_actions()
        datas = [item.action.data for item in result.items]
        assert any(MenuAction.SEARCH_ADDRESS in d for d in datas)


class TestQuickReplyBuilderCreateLocationRequest:
    """測試 QuickReplyBuilder.create_location_request"""

    def test_returns_quick_reply_with_location_action(self):
        """回傳 QuickReply 包含 1 個 LocationAction"""
        result = QuickReplyBuilder.create_location_request()
        assert isinstance(result, QuickReply)
        assert len(result.items) == 1
        assert isinstance(result.items[0].action, LocationAction)

    def test_location_action_label(self):
        """LocationAction 標籤為分享位置"""
        result = QuickReplyBuilder.create_location_request()
        assert '分享' in result.items[0].action.label


class TestQuickReplyBuilderCreateRecentSearchQuickReply:
    """測試 QuickReplyBuilder.create_recent_search_quick_reply"""

    def test_returns_none_when_no_history(self):
        """無搜尋紀錄時回傳 None"""
        with patch('line_bot.builders.flex_builder.SearchHistoryService.get_search_history', return_value=[]):
            result = QuickReplyBuilder.create_recent_search_quick_reply('user123')
        assert result is None

    def test_returns_quick_reply_with_history(self):
        """有搜尋紀錄時回傳 QuickReply"""
        history = [
            {'keyword': '星巴克', 'type': 'shop_name', 'place_id': 'p1'},
            {'keyword': '信義路', 'type': 'address', 'place_id': None},
        ]
        with patch('line_bot.builders.flex_builder.SearchHistoryService.get_search_history', return_value=history):
            result = QuickReplyBuilder.create_recent_search_quick_reply('user123')
        assert isinstance(result, QuickReply)
        assert len(result.items) == 2

    def test_shop_name_uses_coffee_icon(self):
        """shop_name 類型使用 ☕️ 圖示"""
        history = [{'keyword': '星巴克', 'type': 'shop_name', 'place_id': None}]
        with patch('line_bot.builders.flex_builder.SearchHistoryService.get_search_history', return_value=history):
            result = QuickReplyBuilder.create_recent_search_quick_reply('user123')
        assert '☕️' in result.items[0].action.label

    def test_address_type_uses_pin_icon(self):
        """address 類型使用 📍 圖示"""
        history = [{'keyword': '信義路', 'type': 'address', 'place_id': None}]
        with patch('line_bot.builders.flex_builder.SearchHistoryService.get_search_history', return_value=history):
            result = QuickReplyBuilder.create_recent_search_quick_reply('user123')
        assert '📍' in result.items[0].action.label

    def test_label_is_truncated_to_18_chars(self):
        """標籤超過 18 字元時截斷"""
        long_keyword = 'a' * 20
        history = [{'keyword': long_keyword, 'type': 'shop_name', 'place_id': None}]
        with patch('line_bot.builders.flex_builder.SearchHistoryService.get_search_history', return_value=history):
            result = QuickReplyBuilder.create_recent_search_quick_reply('user123')
        assert len(result.items[0].action.label) <= 18

    def test_history_limited_to_five_items(self):
        """最多顯示 5 筆搜尋紀錄"""
        history = [{'keyword': f'店家{i}', 'type': 'shop_name', 'place_id': None} for i in range(8)]
        with patch('line_bot.builders.flex_builder.SearchHistoryService.get_search_history', return_value=history):
            result = QuickReplyBuilder.create_recent_search_quick_reply('user123')
        assert len(result.items) == 5

    def test_display_text_is_keyword(self):
        """PostbackAction 的 display_text 為搜尋關鍵字本身"""
        history = [{'keyword': '星巴克', 'type': 'shop_name', 'place_id': None}]
        with patch('line_bot.builders.flex_builder.SearchHistoryService.get_search_history', return_value=history):
            result = QuickReplyBuilder.create_recent_search_quick_reply('user123')
        assert result.items[0].action.display_text == '星巴克'
