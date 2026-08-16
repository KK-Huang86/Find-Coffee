import threading

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

    def test_multiple_shops_passes_resolved_photo_url_map_as_override(self):
        """多筆結果分支會呼叫平行解析方法，並將對照表中對應的 URL 傳入每筆 create_shop_flex_message 的 photo_url_override"""
        api = MagicMock()
        shops = [{'place_id': f'p{i}'} for i in range(5)]
        info_ds = [{'place_id': f'p{i}', 'name': f'shop{i}'} for i in range(5)]
        photo_url_map = {f'p{i}': f'https://example.com/p{i}.jpg' for i in range(5)}

        with patch(
            'line_bot.builders.message_sender.LineMessageBuilder._get_or_create_shop_info',
            side_effect=[(info_d, MagicMock()) for info_d in info_ds],
        ), \
            patch.object(
                LineMessageBuilder, '_resolve_photo_urls_concurrently', return_value=photo_url_map
            ) as mock_resolve, \
            patch.object(
                FlexMessageBuilder, 'create_shop_flex_message', return_value={'type': 'bubble'}
            ) as mock_flex:
            LineMessageBuilder.send_shop_result(api, 'tok', shops, self._make_user())

        mock_resolve.assert_called_once_with(info_ds)
        for i, info_d in enumerate(info_ds):
            mock_flex.assert_any_call(
                info_d, is_multiple=True, photo_url_override=photo_url_map[f'p{i}']
            )


@pytest.mark.django_db
class TestLineMessageBuilderResolvePhotoUrlsConcurrently:
    """測試 LineMessageBuilder._resolve_photo_urls_concurrently"""

    def _make_info(self, place_id):
        return {'place_id': place_id, 'photo_reference': f'ref-{place_id}', 'photo_s3_url': ''}

    def test_calls_get_photo_url_with_sync_resolve_allowed_for_each_info(self):
        """對每筆 info 平行呼叫 get_photo_url，皆帶入 allow_sync_resolve=True"""
        infos = [self._make_info('p1'), self._make_info('p2'), self._make_info('p3')]

        def fake_get_photo_url(info, allow_sync_resolve=True):
            return f'https://example.com/{info["place_id"]}.jpg'

        with patch.object(FlexMessageBuilder, 'get_photo_url', side_effect=fake_get_photo_url) as mock_get, \
             patch('line_bot.builders.message_sender.connections'):
            result = LineMessageBuilder._resolve_photo_urls_concurrently(infos)

        assert result == {
            'p1': 'https://example.com/p1.jpg',
            'p2': 'https://example.com/p2.jpg',
            'p3': 'https://example.com/p3.jpg',
        }
        for call in mock_get.call_args_list:
            assert call.kwargs.get('allow_sync_resolve') is True or call.args[1] is True

    def test_single_failure_falls_back_to_default_without_affecting_others(self):
        """某一筆 get_photo_url 拋出例外時，該筆回退預設圖，不影響其他筆的正確結果"""
        infos = [self._make_info('p1'), self._make_info('p2'), self._make_info('p3')]

        def fake_get_photo_url(info, allow_sync_resolve=True):
            if info['place_id'] == 'p2':
                raise RuntimeError('boom')
            return f'https://example.com/{info["place_id"]}.jpg'

        with patch.object(FlexMessageBuilder, 'get_photo_url', side_effect=fake_get_photo_url), \
             patch('line_bot.builders.message_sender.connections'):
            result = LineMessageBuilder._resolve_photo_urls_concurrently(infos)

        assert result['p1'] == 'https://example.com/p1.jpg'
        assert result['p2'] == FlexMessageBuilder.DEFAULT_PHOTO_URL
        assert result['p3'] == 'https://example.com/p3.jpg'

    def test_closes_all_db_connections_once_per_info(self):
        """每次 worker 呼叫結束後皆呼叫 connections.close_all()，次數與 infos 筆數一致"""
        infos = [self._make_info('p1'), self._make_info('p2')]

        with patch.object(FlexMessageBuilder, 'get_photo_url', return_value='https://example.com/x.jpg'), \
             patch('line_bot.builders.message_sender.connections') as mock_connections:
            LineMessageBuilder._resolve_photo_urls_concurrently(infos)

        assert mock_connections.close_all.call_count == len(infos)

    def test_empty_infos_returns_empty_dict(self):
        """infos 為空時直接回傳空字典"""
        with patch.object(FlexMessageBuilder, 'get_photo_url') as mock_get:
            result = LineMessageBuilder._resolve_photo_urls_concurrently([])

        assert result == {}
        mock_get.assert_not_called()

    def test_calls_run_concurrently_not_sequentially(self):
        """
        證明真正並行（非序列迴圈偽裝），用 Barrier 同步而非量測牆鐘時間，避免 CI 負載造成 flaky：
        Barrier 要求所有 3 個 worker 皆到達等待點才會一起放行；若實作退化為序列呼叫，
        每次只會有 1 個 worker 到達，其餘 2 個未到位，Barrier 在 timeout 後拋出
        BrokenBarrierError，該筆 get_photo_url 呼叫失敗、回退為 DEFAULT_PHOTO_URL，
        導致最終結果與預期的真實 URL 不符，測試因此失敗。
        """
        infos = [self._make_info(f'p{i}') for i in range(3)]
        barrier = threading.Barrier(len(infos), timeout=1.0)

        def fake_get_photo_url(info, allow_sync_resolve=True):
            barrier.wait()
            return f'https://example.com/{info["place_id"]}.jpg'

        with patch.object(FlexMessageBuilder, 'get_photo_url', side_effect=fake_get_photo_url), \
             patch('line_bot.builders.message_sender.connections'):
            result = LineMessageBuilder._resolve_photo_urls_concurrently(infos)

        assert result == {
            f'p{i}': f'https://example.com/p{i}.jpg' for i in range(len(infos))
        }
