import pytest
from unittest.mock import MagicMock, patch

from linebot.v3.messaging import FlexMessage

from cafe.models import Cafe
from line_bot.constants import MenuAction, UserState, QUOTA_EXCEEDED
from line_bot.handlers.postback_actions import (
    handle_favorite,
    handle_unfavorite,
    handle_view_detail,
    handle_recent_search,
    handle_menu,
    handle_all_pet_search,
    handle_description_search_text,
    handle_ask_ai,
)
from cafe.services.search_service import CafeSearchResult
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
class TestHandleAskAi:
    """測試 handle_ask_ai：優先讀 ai_summary，空值時當場產生並存入"""

    MODULE = 'line_bot.handlers.postback_actions'

    def _reply_text(self, mock_api):
        return mock_api.reply_message.call_args[0][0].messages[0].text

    def _patch_db_lookup(self):
        """每次呼叫都從 DB 重讀，模擬真實的 get_or_create_cafe_info"""
        def _lookup(place_id, user_id):
            cafe = Cafe.objects.filter(place_id=place_id).first()
            return (cafe.to_dict(), cafe) if cafe else (None, None)
        return patch(f'{self.MODULE}.get_or_create_cafe_info', side_effect=_lookup)

    def _patch_quota(self, can_increment=True):
        return (
            patch(f'{self.MODULE}.ApiUsageService.try_increment_ai_calls', return_value=can_increment),
            patch(f'{self.MODULE}.ApiUsageService.revert_ai_call'),
        )

    def test_missing_place_id_replies_not_found(self):
        """缺 place_id 時回覆找不到，不查詢店家"""
        user = UserFactory()
        mock_api = MagicMock()

        with patch(f'{self.MODULE}.get_or_create_cafe_info') as mock_get:
            handle_ask_ai(mock_api, 'test_token', user, {})

        mock_get.assert_not_called()
        assert self._reply_text(mock_api) == '找不到該咖啡店'

    def test_cafe_not_found_replies_not_found(self):
        """找不到店家時回覆找不到，不呼叫 Groq"""
        user = UserFactory()
        mock_api = MagicMock()

        with patch(f'{self.MODULE}.get_or_create_cafe_info', return_value=(None, None)), \
             patch(f'{self.MODULE}.GroqAPI.summarize_for_search') as mock_summarize:
            handle_ask_ai(mock_api, 'test_token', user, {'place_id': 'invalid'})

        mock_summarize.assert_not_called()
        assert self._reply_text(mock_api) == '找不到該咖啡店'

    def test_google_quota_exceeded_replies_quota_message(self):
        """建立店家時 Google 額度用盡，回覆額度訊息"""
        user = UserFactory()
        mock_api = MagicMock()

        with patch(f'{self.MODULE}.get_or_create_cafe_info', return_value=(QUOTA_EXCEEDED, None)), \
             patch(f'{self.MODULE}.GroqAPI.summarize_for_search') as mock_summarize:
            handle_ask_ai(mock_api, 'test_token', user, {'place_id': 'pid'})

        mock_summarize.assert_not_called()
        assert self._reply_text(mock_api) == '本月 API 查詢額度已達上限 😢'

    def test_existing_summary_replies_without_groq_or_quota(self):
        """已有 ai_summary：直接回覆，不呼叫 Groq、不扣額度"""
        user = UserFactory()
        cafe = CafeFactory(name='安靜咖啡', ai_summary='適合讀書的安靜咖啡店。', reviews=['安靜'])
        mock_api = MagicMock()
        increment, revert = self._patch_quota()

        with self._patch_db_lookup(), increment as mock_increment, revert, \
             patch(f'{self.MODULE}.GroqAPI.summarize_for_search') as mock_summarize:
            handle_ask_ai(mock_api, 'test_token', user, {'place_id': cafe.place_id})

        mock_summarize.assert_not_called()
        mock_increment.assert_not_called()
        assert self._reply_text(mock_api) == '🤖 AI 評價｜安靜咖啡\n\n適合讀書的安靜咖啡店。'

    @pytest.mark.parametrize('empty_summary', [None, ''])
    def test_missing_summary_generates_and_saves(self, empty_summary):
        """ai_summary 為空：扣使用者額度、呼叫 Groq 一次、寫入 DB 並回覆"""
        user = UserFactory()
        cafe = CafeFactory(name='新店', ai_summary=empty_summary, reviews=['拿鐵好喝', '有插座'])
        mock_api = MagicMock()
        increment, revert = self._patch_quota()

        with self._patch_db_lookup(), increment as mock_increment, revert as mock_revert, \
             patch(f'{self.MODULE}.GroqAPI.summarize_for_search', return_value='新產生的摘要') as mock_summarize:
            handle_ask_ai(mock_api, 'test_token', user, {'place_id': cafe.place_id})

        mock_increment.assert_called_once_with(user.id)
        mock_revert.assert_not_called()
        mock_summarize.assert_called_once_with(name='新店', reviews=['拿鐵好喝', '有插座'])
        cafe.refresh_from_db()
        assert cafe.ai_summary == '新產生的摘要'
        assert self._reply_text(mock_api) == '🤖 AI 評價｜新店\n\n新產生的摘要'

    def test_save_does_not_touch_other_fields(self):
        """寫入 ai_summary 不影響其他欄位"""
        user = UserFactory()
        cafe = CafeFactory(ai_summary=None, reviews=['好喝'], favorite_count=5, name='原名')
        mock_api = MagicMock()
        increment, revert = self._patch_quota()

        with self._patch_db_lookup(), increment, revert, \
             patch(f'{self.MODULE}.GroqAPI.summarize_for_search', return_value='摘要'):
            handle_ask_ai(mock_api, 'test_token', user, {'place_id': cafe.place_id})

        cafe.refresh_from_db()
        assert cafe.favorite_count == 5
        assert cafe.name == '原名'

    def test_repeated_click_calls_groq_only_once(self):
        """第一次點擊產生並寫入後，第二次點擊直接讀 DB"""
        user = UserFactory()
        cafe = CafeFactory(ai_summary=None, reviews=['好喝'])
        mock_api = MagicMock()
        increment, revert = self._patch_quota()

        with self._patch_db_lookup(), increment as mock_increment, revert, \
             patch(f'{self.MODULE}.GroqAPI.summarize_for_search', return_value='摘要') as mock_summarize:
            handle_ask_ai(mock_api, 'token_1', user, {'place_id': cafe.place_id})
            handle_ask_ai(mock_api, 'token_2', user, {'place_id': cafe.place_id})

        assert mock_summarize.call_count == 1
        assert mock_increment.call_count == 1
        assert self._reply_text(mock_api).endswith('摘要')

    @pytest.mark.parametrize('reviews', [[], None])
    def test_no_reviews_replies_insufficient_without_groq_or_quota(self, reviews):
        """ai_summary 為空且沒有評論：回覆評論不足，不呼叫 Groq、不扣額度"""
        user = UserFactory()
        cafe = CafeFactory(ai_summary=None, reviews=reviews)
        mock_api = MagicMock()
        increment, revert = self._patch_quota()

        with self._patch_db_lookup(), increment as mock_increment, revert, \
             patch(f'{self.MODULE}.GroqAPI.summarize_for_search') as mock_summarize:
            handle_ask_ai(mock_api, 'test_token', user, {'place_id': cafe.place_id})

        mock_summarize.assert_not_called()
        mock_increment.assert_not_called()
        assert self._reply_text(mock_api) == '這間店目前評論不足，AI 暫時無法評價 😢'

    def test_user_quota_exhausted_replies_quota_message(self):
        """使用者 AI 額度用盡：不呼叫 Groq，ai_summary 維持空值"""
        user = UserFactory()
        cafe = CafeFactory(ai_summary=None, reviews=['好喝'])
        mock_api = MagicMock()
        increment, revert = self._patch_quota(can_increment=False)

        with self._patch_db_lookup(), increment, revert as mock_revert, \
             patch(f'{self.MODULE}.GroqAPI.summarize_for_search') as mock_summarize:
            handle_ask_ai(mock_api, 'test_token', user, {'place_id': cafe.place_id})

        mock_summarize.assert_not_called()
        mock_revert.assert_not_called()
        cafe.refresh_from_db()
        assert cafe.ai_summary is None
        assert self._reply_text(mock_api) == '本月 AI 評價額度已達上限 😢'

    @pytest.mark.parametrize('groq_result', [None, ''])
    def test_groq_failure_reverts_quota_and_keeps_summary(self, groq_result):
        """Groq 回傳空結果：回復使用者額度，ai_summary 維持原值"""
        user = UserFactory()
        cafe = CafeFactory(ai_summary=None, reviews=['好喝'])
        mock_api = MagicMock()
        increment, revert = self._patch_quota()

        with self._patch_db_lookup(), increment, revert as mock_revert, \
             patch(f'{self.MODULE}.GroqAPI.summarize_for_search', return_value=groq_result):
            handle_ask_ai(mock_api, 'test_token', user, {'place_id': cafe.place_id})

        mock_revert.assert_called_once_with(user.id)
        cafe.refresh_from_db()
        assert cafe.ai_summary is None
        assert self._reply_text(mock_api) == 'AI 評價暫時無法使用，請稍後再試'

    def test_background_task_wrote_first_keeps_db_version(self):
        """等待 Groq 期間背景任務先寫入：不覆蓋 DB，回覆 DB 版本"""
        user = UserFactory()
        cafe = CafeFactory(name='競爭店', ai_summary=None, reviews=['好喝'])
        mock_api = MagicMock()
        increment, revert = self._patch_quota()

        def _summarize_while_task_writes(**kwargs):
            Cafe.objects.filter(pk=cafe.pk).update(ai_summary='背景任務摘要')
            return '點擊產生的摘要'

        with self._patch_db_lookup(), increment, revert as mock_revert, \
             patch(f'{self.MODULE}.GroqAPI.summarize_for_search', side_effect=_summarize_while_task_writes):
            handle_ask_ai(mock_api, 'test_token', user, {'place_id': cafe.place_id})

        mock_revert.assert_not_called()
        cafe.refresh_from_db()
        assert cafe.ai_summary == '背景任務摘要'
        assert self._reply_text(mock_api) == '🤖 AI 評價｜競爭店\n\n背景任務摘要'

    def test_does_not_use_redis_cache(self):
        """AI 評價只存 DB，不再讀寫 Redis 快取"""
        user = UserFactory()
        cafe = CafeFactory(ai_summary=None, reviews=['好喝'])
        mock_api = MagicMock()
        increment, revert = self._patch_quota()

        with self._patch_db_lookup(), increment, revert, \
             patch('django.core.cache.cache') as mock_cache, \
             patch(f'{self.MODULE}.GroqAPI.summarize_for_search', return_value='摘要'):
            handle_ask_ai(mock_api, 'test_token', user, {'place_id': cafe.place_id})

        mock_cache.get.assert_not_called()
        mock_cache.set.assert_not_called()


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

    def test_favorites_shows_list_bubble(self):
        """FAVORITES 有收藏時，回傳列表 bubble"""
        user = UserFactory()
        for cafe in [CafeFactory() for _ in range(3)]:
            user.favorites.create(cafe=cafe)
        mock_api = MagicMock()

        with patch('line_bot.handlers.postback_actions.FavoritesPageBuilder.build_page_message',
                   return_value=MagicMock()) as mock_build, \
             patch('line_bot.handlers.postback_actions.ReplyMessageRequest', return_value=MagicMock()):
            handle_menu(mock_api, 'test_token', user, {'type': MenuAction.FAVORITES})

        mock_build.assert_called_once()
        mock_api.reply_message.assert_called_once()

    def test_favorites_next_page_button_shown_when_more(self):
        """收藏超過 FAVORITES_PAGE_SIZE 時，quick_reply 包含「下一頁」"""
        from line_bot.handlers.postback_actions import FAVORITES_PAGE_SIZE
        user = UserFactory()
        for cafe in [CafeFactory() for _ in range(FAVORITES_PAGE_SIZE + 1)]:
            user.favorites.create(cafe=cafe)
        mock_api = MagicMock()

        flex_msg_mock = MagicMock()
        with patch('line_bot.handlers.postback_actions.FavoritesPageBuilder.build_page_message',
                   return_value=flex_msg_mock), \
             patch('line_bot.handlers.postback_actions.ReplyMessageRequest', return_value=MagicMock()):
            handle_menu(mock_api, 'test_token', user, {'type': MenuAction.FAVORITES})

        # quick_reply 被設定到 flex_msg_mock 上
        assert flex_msg_mock.quick_reply is not None

    def test_favorites_no_next_page_button_when_exact_fit(self):
        """收藏剛好等於 FAVORITES_PAGE_SIZE 時，不顯示「下一頁」"""
        from line_bot.handlers.postback_actions import FAVORITES_PAGE_SIZE
        user = UserFactory()
        for cafe in [CafeFactory() for _ in range(FAVORITES_PAGE_SIZE)]:
            user.favorites.create(cafe=cafe)
        mock_api = MagicMock()

        flex_msg_mock = MagicMock()
        flex_msg_mock.quick_reply = None
        with patch('line_bot.handlers.postback_actions.FavoritesPageBuilder.build_page_message',
                   return_value=flex_msg_mock), \
             patch('line_bot.handlers.postback_actions.ReplyMessageRequest', return_value=MagicMock()):
            handle_menu(mock_api, 'test_token', user, {'type': MenuAction.FAVORITES})

        assert flex_msg_mock.quick_reply is None

    def test_recent_search_no_history_replies_prompt(self):
        """RECENT_SEARCH 無紀錄時，回覆提示訊息"""
        user = UserFactory()
        mock_api = MagicMock()

        with patch('line_bot.handlers.postback_actions.QuickReplyBuilder.create_recent_search_quick_reply') as mock_qr:
            mock_qr.return_value = None
            handle_menu(mock_api, 'test_token', user, {'type': MenuAction.RECENT_SEARCH})

        call_args = mock_api.reply_message.call_args[0][0]
        assert '搜尋紀錄' in call_args.messages[0].text

    def test_more_info_shows_feature_menu(self):
        """MORE_INFO 顯示功能選單（含 QuickReply）"""
        user = UserFactory()
        mock_api = MagicMock()

        handle_menu(mock_api, 'test_token', user, {'type': MenuAction.MORE_INFO})

        mock_api.reply_message.assert_called_once()
        call_args = mock_api.reply_message.call_args[0][0]
        assert call_args.messages[0].quick_reply is not None

    def test_unknown_type_does_not_reply(self):
        """未知的 menu type，不觸發任何回覆"""
        user = UserFactory()
        mock_api = MagicMock()

        handle_menu(mock_api, 'test_token', user, {'type': 'unknown_action'})

        mock_api.reply_message.assert_not_called()


@pytest.mark.django_db
class TestHandleAllPetSearch:
    """測試 handle_all_pet_search"""

    def test_no_cafes_replies_not_found(self):
        """DB 沒有有貓貓狗狗的店，回覆找不到訊息"""
        user = UserFactory()
        mock_api = MagicMock()

        handle_all_pet_search(mock_api, 'test_token', user, {})

        call_args = mock_api.reply_message.call_args[0][0]
        assert '還沒有' in call_args.messages[0].text

    def test_returns_cafes_with_has_pet_yes(self):
        """has_pet='yes' 的店出現在結果中"""
        user = UserFactory()
        CafeFactory(has_pet='yes')
        mock_api = MagicMock()

        handle_all_pet_search(mock_api, 'test_token', user, {})

        mock_api.reply_message.assert_called_once()

    def test_cafes_without_has_pet_excluded(self):
        """has_pet 非 yes 的店不出現"""
        user = UserFactory()
        CafeFactory(has_pet='no')
        CafeFactory(has_pet=None)
        mock_api = MagicMock()

        handle_all_pet_search(mock_api, 'test_token', user, {})

        call_args = mock_api.reply_message.call_args[0][0]
        assert '還沒有' in call_args.messages[0].text

    def test_returns_at_most_5_results(self):
        """最多回傳 5 筆"""
        user = UserFactory()
        for _ in range(8):
            CafeFactory(has_pet='yes')
        mock_api = MagicMock()

        with patch('line_bot.handlers.postback_actions.FlexMessageBuilder.create_shop_flex_message',
                   return_value=MagicMock()), \
             patch('line_bot.handlers.postback_actions.FlexContainer.from_dict', return_value=MagicMock()), \
             patch('line_bot.handlers.postback_actions.FlexMessage', return_value=MagicMock()), \
             patch('line_bot.handlers.postback_actions.ReplyMessageRequest', return_value=MagicMock()):
            handle_all_pet_search(mock_api, 'test_token', user, {})

        mock_api.reply_message.assert_called_once()


@pytest.mark.django_db
class TestMenuPetSearch:
    """測試點選有貓貓狗狗按鈕時，回覆含 QuickReply"""

    def test_pet_search_sets_state_and_shows_quick_reply(self):
        """點選有貓貓狗狗按鈕，設定 WAITING_PET_DISTRICT 並顯示全部查詢 QuickReply"""
        user = UserFactory()
        mock_api = MagicMock()

        with patch('line_bot.handlers.postback_actions.StateManager.set_state') as mock_state:
            handle_menu(mock_api, 'test_token', user, {'type': MenuAction.PET_SEARCH})

        mock_state.assert_called_once_with(user.line_user_id, UserState.WAITING_PET_DISTRICT)
        call_args = mock_api.reply_message.call_args[0][0]
        assert call_args.messages[0].quick_reply is not None


@pytest.mark.django_db
class TestHandleNextPage:
    """測試 handle_next_page"""

    def _mock_flex(self):
        return patch('line_bot.handlers.postback_actions.FlexMessageBuilder.create_shop_flex_message',
                     return_value=MagicMock()), \
               patch('line_bot.handlers.postback_actions.FlexContainer.from_dict', return_value=MagicMock()), \
               patch('line_bot.handlers.postback_actions.FlexMessage', return_value=MagicMock()), \
               patch('line_bot.handlers.postback_actions.ReplyMessageRequest', return_value=MagicMock())

    def test_district_next_page_returns_results(self):
        """search_type=district：回傳下一頁工作友善咖啡"""
        from line_bot.handlers.postback_actions import handle_next_page
        for _ in range(3):
            CafeFactory(address='大安區信義路', limited_time='no', has_socket='yes')
        user = MagicMock()
        mock_api = MagicMock()

        with patch('line_bot.handlers.postback_actions.FlexMessageBuilder.create_shop_flex_message',
                   return_value=MagicMock()), \
             patch('line_bot.handlers.postback_actions.FlexContainer.from_dict', return_value=MagicMock()), \
             patch('line_bot.handlers.postback_actions.FlexMessage', return_value=MagicMock()), \
             patch('line_bot.handlers.postback_actions.ReplyMessageRequest', return_value=MagicMock()):
            handle_next_page(mock_api, 'test_token', user, {
                'search_type': 'district', 'keyword': '大安區', 'offset': '0'
            })

        mock_api.reply_message.assert_called_once()

    def test_unknown_search_type_does_not_reply(self):
        """未知 search_type，不觸發任何回覆"""
        from line_bot.handlers.postback_actions import handle_next_page
        user = MagicMock()
        mock_api = MagicMock()

        handle_next_page(mock_api, 'test_token', user, {
            'search_type': 'unknown', 'keyword': '大安區', 'offset': '0'
        })

        mock_api.reply_message.assert_not_called()

    def test_empty_results_replies_empty_msg(self):
        """無結果時，回覆提示文字"""
        from line_bot.handlers.postback_actions import handle_next_page
        user = MagicMock()
        mock_api = MagicMock()

        handle_next_page(mock_api, 'test_token', user, {
            'search_type': 'all_pet', 'keyword': '', 'offset': '0'
        })

        mock_api.reply_message.assert_called_once()
        call_args = mock_api.reply_message.call_args[0][0]
        assert '貓貓狗狗' in call_args.messages[0].text


@pytest.mark.django_db
class TestReplyCafePage:
    """測試 _reply_cafe_page 分頁邏輯"""

    def test_has_more_includes_next_page_button(self):
        """結果超過 PAGE_SIZE 時，quick_reply 包含「下一頁」"""
        from line_bot.handlers.postback_actions import _reply_cafe_page, PAGE_SIZE
        for _ in range(PAGE_SIZE + 1):
            CafeFactory(has_pet='yes')
        cafes_qs = __import__('cafe.models', fromlist=['Cafe']).Cafe.objects.filter(has_pet='yes')
        mock_api = MagicMock()

        flex_msg_mock = MagicMock()
        with patch('line_bot.handlers.postback_actions.FlexMessageBuilder.create_shop_flex_message',
                   return_value=MagicMock()), \
             patch('line_bot.handlers.postback_actions.FlexContainer.from_dict', return_value=MagicMock()), \
             patch('line_bot.handlers.postback_actions.FlexMessage', return_value=flex_msg_mock), \
             patch('line_bot.handlers.postback_actions.ReplyMessageRequest', return_value=MagicMock()), \
             patch('line_bot.handlers.postback_actions.QuickReplyBuilder.create_district_search_actions') as mock_qr:
            mock_qr.return_value = MagicMock()
            _reply_cafe_page(mock_api, 'token', cafes_qs, 0, 'all_pet', '', 'empty', 'alt')

        mock_qr.assert_called_once()
        _, _, _, has_more_arg = mock_qr.call_args[0]
        assert has_more_arg is True

    def test_no_more_pages_omits_next_button(self):
        """結果不超過 PAGE_SIZE 時，has_more=False"""
        from line_bot.handlers.postback_actions import _reply_cafe_page, PAGE_SIZE
        for _ in range(PAGE_SIZE - 1):
            CafeFactory(has_pet='yes')
        cafes_qs = __import__('cafe.models', fromlist=['Cafe']).Cafe.objects.filter(has_pet='yes')
        mock_api = MagicMock()

        with patch('line_bot.handlers.postback_actions.FlexMessageBuilder.create_shop_flex_message',
                   return_value=MagicMock()), \
             patch('line_bot.handlers.postback_actions.FlexContainer.from_dict', return_value=MagicMock()), \
             patch('line_bot.handlers.postback_actions.FlexMessage', return_value=MagicMock()), \
             patch('line_bot.handlers.postback_actions.ReplyMessageRequest', return_value=MagicMock()), \
             patch('line_bot.handlers.postback_actions.QuickReplyBuilder.create_district_search_actions') as mock_qr:
            mock_qr.return_value = MagicMock()
            _reply_cafe_page(mock_api, 'token', cafes_qs, 0, 'all_pet', '', 'empty', 'alt')

        _, _, _, has_more_arg = mock_qr.call_args[0]
        assert has_more_arg is False


@pytest.mark.django_db
class TestMenuDescriptionSearch:
    """測試 MenuAction.DESCRIPTION_SEARCH 入口"""

    def test_sets_state_and_replies_prompt(self):
        """設定等待狀態並回覆輸入提示"""
        user = UserFactory()
        mock_api = MagicMock()

        with patch('line_bot.handlers.postback_actions.StateManager.set_state') as mock_state:
            handle_menu(mock_api, 'test_token', user, {'type': MenuAction.DESCRIPTION_SEARCH})

        mock_state.assert_called_once_with(user.line_user_id, UserState.WAITING_DESCRIPTION_SEARCH)
        call_args = mock_api.reply_message.call_args[0][0]
        assert '描述' in call_args.messages[0].text


@pytest.mark.django_db
class TestHandleDescriptionSearchText:
    """測試 handle_description_search_text"""

    def test_quota_exceeded_replies_quota_message_and_not_generic_not_found(self):
        """quota_exceeded 時回覆額度不足訊息，而非用查無結果訊息猜測"""
        user = UserFactory()
        mock_api = MagicMock()

        with patch(
            'line_bot.handlers.postback_actions.CafeSearchService.search_by_description',
            return_value=CafeSearchResult(status='quota_exceeded', cafes=Cafe.objects.none()),
        ) as mock_search:
            handle_description_search_text(mock_api, 'test_token', user, '安靜的店')

        mock_search.assert_called_once_with('安靜的店', user.id)
        call_args = mock_api.reply_message.call_args[0][0]
        assert '額度' in call_args.messages[0].text

    def test_ok_with_no_results_replies_not_found_message(self):
        """status='ok' 且 cafes 為空時，回覆找不到符合描述的店家"""
        user = UserFactory()
        mock_api = MagicMock()

        with patch(
            'line_bot.handlers.postback_actions.CafeSearchService.search_by_description',
            return_value=CafeSearchResult(status='ok', cafes=Cafe.objects.none()),
        ):
            handle_description_search_text(mock_api, 'test_token', user, '安靜的店')

        call_args = mock_api.reply_message.call_args[0][0]
        assert '找不到' in call_args.messages[0].text

    def test_ok_with_results_replies_flex_carousel(self):
        """status='ok' 且有符合店家時，回覆 Flex Message carousel"""
        user = UserFactory()
        mock_api = MagicMock()
        cafe = CafeFactory(ai_summary='適合安靜工作')

        with patch(
            'line_bot.handlers.postback_actions.CafeSearchService.search_by_description',
            return_value=CafeSearchResult(status='ok', cafes=Cafe.objects.filter(id=cafe.id)),
        ):
            handle_description_search_text(mock_api, 'test_token', user, '安靜的店')

        mock_api.reply_message.assert_called_once()
        call_args = mock_api.reply_message.call_args[0][0]
        assert isinstance(call_args.messages[0], FlexMessage)

    def test_blank_input_does_not_crash_and_replies(self):
        """空白輸入不拋例外，仍會回覆訊息（走查無結果路徑）"""
        user = UserFactory()
        mock_api = MagicMock()

        with patch(
            'line_bot.handlers.postback_actions.CafeSearchService.search_by_description',
            return_value=CafeSearchResult(status='ok', cafes=Cafe.objects.none()),
        ) as mock_search:
            handle_description_search_text(mock_api, 'test_token', user, '   ')

        mock_search.assert_called_once_with('   ', user.id)
        mock_api.reply_message.assert_called_once()
