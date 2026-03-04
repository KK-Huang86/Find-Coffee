import pytest
from unittest.mock import MagicMock, patch

from line_bot.constants import MenuAction, UserState
from line_bot.handlers.postback_actions import (
    handle_favorite,
    handle_unfavorite,
    handle_view_detail,
    handle_recent_search,
    handle_menu,
)
from line_bot.tests.factories import CafeFactory, UserFactory


@pytest.mark.django_db
class TestHandleFavorite:
    """測試 handle_favorite"""

    def test_cafe_not_found_replies_error(self):
        """找不到咖啡店時，回覆錯誤訊息"""
        user = UserFactory()
        mock_api = MagicMock()

        with patch('line_bot.handlers.postback_actions.get_or_create_cafe_info') as mock_get:
            mock_get.return_value = (None, None)
            handle_favorite(mock_api, 'test_token', user, {'place_id': 'invalid_id'})

        call_args = mock_api.reply_message.call_args[0][0]
        assert call_args.messages[0].text == '找不到該咖啡店'

    def test_adds_favorite_and_replies_message(self):
        """成功收藏，回覆結果訊息"""
        user = UserFactory()
        mock_api = MagicMock()
        info_d = {'place_id': 'test_place_id', 'name': '測試咖啡店'}

        with patch('line_bot.handlers.postback_actions.get_or_create_cafe_info') as mock_get, \
             patch('line_bot.handlers.postback_actions.FavoritesManager.add_favorite') as mock_add:
            mock_get.return_value = (info_d, MagicMock())
            mock_add.return_value = (True, '收藏成功！')
            handle_favorite(mock_api, 'test_token', user, {'place_id': 'test_place_id'})

        mock_add.assert_called_once_with(user, info_d)
        call_args = mock_api.reply_message.call_args[0][0]
        assert call_args.messages[0].text == '收藏成功！'


@pytest.mark.django_db
class TestHandleUnfavorite:
    """測試 handle_unfavorite"""

    def test_cafe_not_in_db_replies_error(self):
        """DB 找不到咖啡店，回覆錯誤訊息"""
        user = UserFactory()
        mock_api = MagicMock()

        handle_unfavorite(mock_api, 'test_token', user, {'place_id': 'nonexistent_id'})

        call_args = mock_api.reply_message.call_args[0][0]
        assert '找不到' in call_args.messages[0].text

    def test_removes_favorite_and_replies_message(self):
        """成功取消收藏，回覆結果訊息"""
        user = UserFactory()
        cafe = CafeFactory()
        mock_api = MagicMock()

        with patch('line_bot.handlers.postback_actions.FavoritesManager.remove_favorite') as mock_remove:
            mock_remove.return_value = (True, '已取消收藏')
            handle_unfavorite(mock_api, 'test_token', user, {'place_id': cafe.place_id})

        mock_remove.assert_called_once()
        call_args = mock_api.reply_message.call_args[0][0]
        assert call_args.messages[0].text == '已取消收藏'


@pytest.mark.django_db
class TestHandleViewDetail:
    """測試 handle_view_detail"""

    def test_cafe_not_found_replies_error(self):
        """找不到咖啡店，回覆錯誤訊息"""
        user = UserFactory()
        mock_api = MagicMock()

        with patch('line_bot.handlers.postback_actions.get_or_create_cafe_info') as mock_get:
            mock_get.return_value = (None, None)
            handle_view_detail(mock_api, 'test_token', user, {'place_id': 'invalid_id'})

        call_args = mock_api.reply_message.call_args[0][0]
        assert call_args.messages[0].text == '找不到此咖啡店'

    def test_shows_detail_when_not_favorited(self):
        """顯示咖啡店詳情（未收藏）"""
        user = UserFactory()
        cafe = CafeFactory()
        mock_api = MagicMock()
        info_d = cafe.to_dict()

        with patch('line_bot.handlers.postback_actions.get_or_create_cafe_info') as mock_get, \
             patch('line_bot.handlers.postback_actions.reply_cafe_detail') as mock_reply:
            mock_get.return_value = (info_d, cafe)
            handle_view_detail(mock_api, 'test_token', user, {'place_id': cafe.place_id})

        mock_reply.assert_called_once_with(mock_api, 'test_token', info_d, False)

    def test_shows_detail_when_already_favorited(self):
        """顯示咖啡店詳情（已收藏）"""
        user = UserFactory()
        cafe = CafeFactory()
        user.favorites.create(cafe=cafe)
        mock_api = MagicMock()
        info_d = cafe.to_dict()

        with patch('line_bot.handlers.postback_actions.get_or_create_cafe_info') as mock_get, \
             patch('line_bot.handlers.postback_actions.reply_cafe_detail') as mock_reply:
            mock_get.return_value = (info_d, cafe)
            handle_view_detail(mock_api, 'test_token', user, {'place_id': cafe.place_id})

        mock_reply.assert_called_once_with(mock_api, 'test_token', info_d, True)


@pytest.mark.django_db
class TestHandleRecentSearch:
    """測試 handle_recent_search"""

    def test_returns_early_without_keyword(self):
        """無 keyword，不觸發任何回覆"""
        user = UserFactory()
        mock_api = MagicMock()

        handle_recent_search(mock_api, 'test_token', user, {'type': 'shop_name'})

        mock_api.reply_message.assert_not_called()

    def test_handles_shop_name_search(self):
        """search_type='shop_name'，呼叫店名搜尋函式"""
        user = UserFactory()
        mock_api = MagicMock()

        with patch('line_bot.handlers.postback_actions._handle_shop_name_search') as mock_shop:
            handle_recent_search(
                mock_api, 'test_token', user,
                {'type': 'shop_name', 'keyword': '星巴克'}
            )

        mock_shop.assert_called_once_with(
            mock_api, 'test_token', user, user.line_user_id, '星巴克', None
        )

    def test_handles_address_search(self):
        """search_type='address'，呼叫地址搜尋函式"""
        user = UserFactory()
        mock_api = MagicMock()

        with patch('line_bot.handlers.postback_actions._handle_address_search') as mock_addr:
            handle_recent_search(
                mock_api, 'test_token', user,
                {'type': 'address', 'keyword': '信義路'}
            )

        mock_addr.assert_called_once_with(
            mock_api, 'test_token', user, user.line_user_id, '信義路'
        )


@pytest.mark.django_db
class TestHandleMenu:
    """測試 handle_menu"""

    def test_search_shop_name_sets_state_and_replies(self):
        """SEARCH_SHOP_NAME：設定等待狀態並回覆提示"""
        user = UserFactory()
        mock_api = MagicMock()

        with patch('line_bot.handlers.postback_actions.StateManager.set_state') as mock_state:
            handle_menu(mock_api, 'test_token', user, {'type': MenuAction.SEARCH_SHOP_NAME})

        mock_state.assert_called_once_with(user.line_user_id, UserState.WAITING_SHOP_NAME)
        call_args = mock_api.reply_message.call_args[0][0]
        assert '咖啡店名稱' in call_args.messages[0].text

    def test_search_address_sets_state_and_replies(self):
        """SEARCH_ADDRESS：設定等待狀態並回覆提示"""
        user = UserFactory()
        mock_api = MagicMock()

        with patch('line_bot.handlers.postback_actions.StateManager.set_state') as mock_state:
            handle_menu(mock_api, 'test_token', user, {'type': MenuAction.SEARCH_ADDRESS})

        mock_state.assert_called_once_with(user.line_user_id, UserState.WAITING_ADDRESS)

    def test_favorites_empty_replies_prompt(self):
        """FAVORITES 無收藏時，回覆引導訊息"""
        user = UserFactory()
        mock_api = MagicMock()

        handle_menu(mock_api, 'test_token', user, {'type': MenuAction.FAVORITES})

        call_args = mock_api.reply_message.call_args[0][0]
        assert '沒有收藏' in call_args.messages[0].text

    def test_favorites_few_shows_carousel(self):
        """FAVORITES 收藏 <=5 時，顯示 carousel"""
        user = UserFactory()
        for cafe in [CafeFactory() for _ in range(3)]:
            user.favorites.create(cafe=cafe)
        mock_api = MagicMock()

        with patch('line_bot.handlers.postback_actions.FavoritesMessageBuilder.show_favorites_carousel') as mock_carousel, \
             patch('line_bot.handlers.postback_actions.ReplyMessageRequest'):
            mock_carousel.return_value = MagicMock()
            handle_menu(mock_api, 'test_token', user, {'type': MenuAction.FAVORITES})

        mock_carousel.assert_called_once_with(user)

    def test_favorites_many_shows_list(self):
        """FAVORITES 收藏 >5 時，顯示清單"""
        user = UserFactory()
        for cafe in [CafeFactory() for _ in range(6)]:
            user.favorites.create(cafe=cafe)
        mock_api = MagicMock()

        with patch('line_bot.handlers.postback_actions.FavoritesMessageBuilder.show_favorites_list') as mock_list, \
             patch('line_bot.handlers.postback_actions.ReplyMessageRequest'):
            mock_list.return_value = MagicMock()
            handle_menu(mock_api, 'test_token', user, {'type': MenuAction.FAVORITES})

        mock_list.assert_called_once_with(user)

    def test_recent_search_no_history_replies_prompt(self):
        """RECENT_SEARCH 無紀錄時，回覆提示訊息"""
        user = UserFactory()
        mock_api = MagicMock()

        with patch('line_bot.handlers.postback_actions.QuickReplyBuilder.create_recent_search_quick_reply') as mock_qr:
            mock_qr.return_value = None
            handle_menu(mock_api, 'test_token', user, {'type': MenuAction.RECENT_SEARCH})

        call_args = mock_api.reply_message.call_args[0][0]
        assert '搜尋紀錄' in call_args.messages[0].text

    def test_more_info_replies_coming_soon(self):
        """MORE_INFO 回覆開發中訊息"""
        user = UserFactory()
        mock_api = MagicMock()

        handle_menu(mock_api, 'test_token', user, {'type': MenuAction.MORE_INFO})

        call_args = mock_api.reply_message.call_args[0][0]
        assert '開發中' in call_args.messages[0].text

    def test_unknown_type_does_not_reply(self):
        """未知的 menu type，不觸發任何回覆"""
        user = UserFactory()
        mock_api = MagicMock()

        handle_menu(mock_api, 'test_token', user, {'type': 'unknown_action'})

        mock_api.reply_message.assert_not_called()
