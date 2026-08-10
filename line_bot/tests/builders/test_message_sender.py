import pytest
from unittest.mock import MagicMock, patch

from linebot.v3.messaging import QuickReply, QuickReplyItem, LocationAction

from line_bot.builders.message_sender import LineMessageBuilder
from line_bot.builders.shop_flex_message import FlexMessageBuilder
from line_bot.constants import QUOTA_EXCEEDED
from cafe.tests.factories import CafeFactory


# LineMessageBuilder.send_shop_result


@pytest.mark.django_db
class TestLineMessageBuilderSendShopResult:
    """測試 LineMessageBuilder.send_shop_result"""

    def _make_user(self, is_favorited=False):
        user = MagicMock()
        user.id = 'user1'
        user.favorites.filter.return_value.exists.return_value = is_favorited
        return user

    def test_empty_shops_replies_not_found(self):
        """shops 為空列表時，回覆『無法取得店家詳細資訊』"""
        api = MagicMock()
        LineMessageBuilder.send_shop_result(api, 'tok', [], self._make_user())
        api.reply_message.assert_called_once()
        req = api.reply_message.call_args[0][0]
        assert req.messages[0].text == '無法取得店家詳細資訊'

    def test_single_shop_quota_exceeded(self):
        """單筆結果但 API 額度超限時，回覆額度超限訊息"""
        api = MagicMock()
        with patch(
            'line_bot.builders.message_sender.LineMessageBuilder._get_or_create_shop_info',
            return_value=(QUOTA_EXCEEDED, None),
        ):
            LineMessageBuilder.send_shop_result(api, 'tok', [{'place_id': 'p1'}], self._make_user())
        req = api.reply_message.call_args[0][0]
        assert '額度已達上限' in req.messages[0].text

    def test_single_shop_info_missing_replies_not_found(self):
        """單筆結果但無法取得詳細資訊時，回覆『無法取得店家詳細資訊』"""
        api = MagicMock()
        with patch(
            'line_bot.builders.message_sender.LineMessageBuilder._get_or_create_shop_info',
            return_value=(None, None),
        ):
            LineMessageBuilder.send_shop_result(api, 'tok', [{'place_id': 'p1'}], self._make_user())
        req = api.reply_message.call_args[0][0]
        assert req.messages[0].text == '無法取得店家詳細資訊'

    def test_single_shop_success_sends_flex_and_button(self):
        """單筆結果成功時，回覆 FlexMessage 與 postback 按鈕，並帶入 quick_reply 與收藏狀態"""
        api = MagicMock()
        info_d = {'place_id': 'p1', 'name': '測試咖啡店'}
        fake_cafe = MagicMock()
        quick_reply = QuickReply(items=[
            QuickReplyItem(action=LocationAction(label='📍 分享目前位置', text='分享位置'))
        ])
        with patch(
            'line_bot.builders.message_sender.LineMessageBuilder._get_or_create_shop_info',
            return_value=(info_d, fake_cafe),
        ), \
            patch.object(FlexMessageBuilder, 'create_shop_flex_message', return_value={'type': 'bubble'}) as mock_flex:
            user = self._make_user(is_favorited=True)
            LineMessageBuilder.send_shop_result(api, 'tok', [{'place_id': 'p1'}], user, quick_reply=quick_reply)

        mock_flex.assert_called_once_with(info_d)
        api.reply_message.assert_called_once()
        req = api.reply_message.call_args[0][0]
        assert len(req.messages) == 2
        button_message = req.messages[1]
        assert button_message.quick_reply == quick_reply
        # is_favorited=True 時應由 PostbackBuilder 產生「取消收藏」標籤
        actions = button_message.to_dict()['template']['actions']
        assert any('取消收藏' in a['label'] for a in actions)

    def test_multiple_shops_uses_db_cache_when_available(self):
        """多筆結果時，已在 DB 中的店家不重複呼叫 _get_or_create_shop_info"""
        CafeFactory(place_id='p1')
        api = MagicMock()
        shops = [{'place_id': 'p1'}, {'place_id': 'p2'}]
        with patch(
            'line_bot.builders.message_sender.LineMessageBuilder._get_or_create_shop_info',
            return_value=({'place_id': 'p2', 'name': 'B'}, MagicMock()),
        ) as mock_get, \
            patch.object(FlexMessageBuilder, 'create_shop_flex_message', return_value={'type': 'bubble'}):
            LineMessageBuilder.send_shop_result(api, 'tok', shops, self._make_user())

        mock_get.assert_called_once_with('p2', 'user1')

    def test_multiple_shops_quota_exceeded_stops_and_replies(self):
        """多筆結果處理過程中遇到額度超限，立即回覆並中止"""
        api = MagicMock()
        shops = [{'place_id': 'p1'}, {'place_id': 'p2'}]
        with patch(
            'line_bot.builders.message_sender.LineMessageBuilder._get_or_create_shop_info',
            return_value=(QUOTA_EXCEEDED, None),
        ):
            LineMessageBuilder.send_shop_result(api, 'tok', shops, self._make_user())
        req = api.reply_message.call_args[0][0]
        assert '額度已達上限' in req.messages[0].text

    def test_multiple_shops_all_missing_uses_http_info_reply(self):
        """多筆結果全部取得失敗時，改用 reply_message_with_http_info 回覆"""
        api = MagicMock()
        shops = [{'place_id': 'p1'}, {'place_id': 'p2'}]
        with patch(
            'line_bot.builders.message_sender.LineMessageBuilder._get_or_create_shop_info',
            return_value=(None, None),
        ):
            LineMessageBuilder.send_shop_result(api, 'tok', shops, self._make_user())
        api.reply_message_with_http_info.assert_called_once()
        req = api.reply_message_with_http_info.call_args[0][0]
        assert req.messages[0].text == '無法取得店家詳細資訊'

    def test_multiple_shops_success_sends_carousel(self):
        """多筆結果成功時，回覆包含 carousel 的訊息"""
        api = MagicMock()
        shops = [{'place_id': 'p1'}, {'place_id': 'p2'}]
        with patch(
            'line_bot.builders.message_sender.LineMessageBuilder._get_or_create_shop_info',
            side_effect=[
                ({'place_id': 'p1'}, MagicMock()),
                ({'place_id': 'p2'}, MagicMock()),
            ],
        ), \
            patch.object(FlexMessageBuilder, 'create_shop_flex_message', return_value={'type': 'bubble'}):
            LineMessageBuilder.send_shop_result(api, 'tok', shops, self._make_user())

        api.reply_message.assert_called_once()
        req = api.reply_message.call_args[0][0]
        assert len(req.messages) == 3
        assert '找到 2 間咖啡店' in req.messages[0].text

    def test_more_than_ten_shops_sends_no_reply(self):
        """目前實作對 >10 筆結果不做任何處理（無 reply），鎖定既有行為避免搬移時意外改變"""
        api = MagicMock()
        shops = [{'place_id': f'p{i}'} for i in range(11)]
        LineMessageBuilder.send_shop_result(api, 'tok', shops, self._make_user())
        api.reply_message.assert_not_called()
        api.reply_message_with_http_info.assert_not_called()
