import pytest
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.utils import timezone
from linebot.v3.messaging import ReplyMessageRequest, TextMessage

from cafe.models import Cafe
from line_bot.constants import QUOTA_EXCEEDED
from line_bot.handlers.helpers import get_or_create_cafe_info, reply_text, reply_cafe_detail
from line_bot.tests.factories import CafeFactory, UserFactory
from utils.distributed_lock import distributed_lock


@pytest.mark.django_db
class TestGetOrCreateCafeInfo:
    """測試 get_or_create_cafe_info"""

    def test_returns_existing_cafe_from_db(self):
        """DB 有資料且未過期，直接回傳"""
        cafe = CafeFactory(last_refreshed=timezone.now())

        with patch('line_bot.handlers.helpers.CafeAttributeMatcher.match_and_sync_attributes') as mock_match:
            mock_match.return_value = False
            info_d, returned_cafe = get_or_create_cafe_info(cafe.place_id, user_id=1)

        assert info_d is not None
        assert returned_cafe == cafe
        assert info_d['place_id'] == cafe.place_id

    # 商業邏輯變更（sync-refresh-stale-cafe-data）：過期判斷、lock 與失敗回退移到 cafe.services.cafe_refresh，
    # 原本直接斷言 refresh_cafe_data(cafe.id) 的兩個測試改為斷言委派給 refresh_cafe_if_stale；
    # 過期 / None 的判斷邊界改由 cafe/tests/test_cafe_refresh.py 覆蓋
    def test_delegates_refresh_to_refresh_cafe_if_stale(self):
        """DB 命中時交由 refresh_cafe_if_stale 決定是否同步刷新"""
        cafe = CafeFactory(last_refreshed=timezone.now() - timedelta(days=31))

        with (
            patch('line_bot.handlers.helpers.refresh_cafe_if_stale', return_value=True) as mock_refresh,
            patch('line_bot.handlers.helpers.CafeAttributeMatcher.match_and_sync_attributes', return_value=False),
        ):
            get_or_create_cafe_info(cafe.place_id, user_id=1)

        mock_refresh.assert_called_once()
        assert mock_refresh.call_args.args[0].id == cafe.id

    def test_returns_refreshed_data_when_stale(self):
        """過期刷新成功時，回傳刷新後的資料"""
        cafe = CafeFactory(name='舊店名', last_refreshed=timezone.now() - timedelta(days=31))

        def fake_refresh(c):
            c.name = '新店名'
            return True

        with (
            patch('line_bot.handlers.helpers.refresh_cafe_if_stale', side_effect=fake_refresh),
            patch('line_bot.handlers.helpers.CafeAttributeMatcher.match_and_sync_attributes', return_value=False),
        ):
            info_d, _ = get_or_create_cafe_info(cafe.place_id, user_id=1)

        assert info_d['name'] == '新店名'

    def test_returns_cached_data_when_refresh_fails(self):
        """刷新失敗時仍回傳既有資料，不回傳 None"""
        cafe = CafeFactory(name='舊店名', last_refreshed=None)

        with (
            patch('line_bot.handlers.helpers.refresh_cafe_if_stale', return_value=False),
            patch('line_bot.handlers.helpers.CafeAttributeMatcher.match_and_sync_attributes', return_value=False),
        ):
            info_d, returned_cafe = get_or_create_cafe_info(cafe.place_id, user_id=1)

        assert info_d['name'] == '舊店名'
        assert returned_cafe == cafe

    def test_returns_quota_exceeded_when_quota_exceeded(self):
        """API 額度不足，回傳 (QUOTA_EXCEEDED, None) 且不呼叫 Google API"""
        with (
            patch('line_bot.handlers.helpers.ApiUsageService.try_increment_detail_calls') as mock_check,
            patch('line_bot.handlers.helpers.GoogleAPI.get_shop_detail') as mock_google,
        ):
            mock_check.return_value = False
            info_d, cafe = get_or_create_cafe_info('some_place_id', user_id=1)

        assert info_d is QUOTA_EXCEEDED
        assert cafe is None
        mock_google.assert_not_called()

    def test_calls_google_api_when_not_in_db(self):
        """DB 無資料，呼叫 Google API 並存入 DB"""
        user = UserFactory()
        place_id = 'test_google_place_id'
        google_data = {
            'place_id': place_id,
            'name': '測試咖啡店',
            'address': '台北市信義區',
            'lat': 25.033,
            'lng': 121.564,
        }

        with (
            patch('line_bot.handlers.helpers.ApiUsageService.try_increment_detail_calls', return_value=True) as mock_increment,
            patch('line_bot.handlers.helpers.GoogleAPI.get_shop_detail') as mock_google,
            patch('line_bot.handlers.helpers.CafeAttributeMatcher.match_and_sync_attributes') as mock_match,
        ):
            mock_google.return_value = google_data
            mock_match.return_value = False
            info_d, cafe = get_or_create_cafe_info(place_id, user.id)

        mock_google.assert_called_once_with(place_id)
        mock_increment.assert_called_once_with(user.id)
        assert info_d is not None
        assert Cafe.objects.filter(place_id=place_id).exists()

    def test_returns_none_when_google_api_fails(self):
        """Google API 回傳 None，回傳 (None, None)"""
        with (
            patch('line_bot.handlers.helpers.ApiUsageService.try_increment_detail_calls', return_value=True),
            patch('line_bot.handlers.helpers.GoogleAPI.get_shop_detail') as mock_google,
        ):
            mock_google.return_value = None
            info_d, cafe = get_or_create_cafe_info('nonexistent_place_id', user_id=1)

        assert info_d is None
        assert cafe is None

    def test_returns_none_when_google_data_missing_place_id(self):
        """Google API 回傳資料缺少 place_id，回傳 (None, None)"""
        with (
            patch('line_bot.handlers.helpers.ApiUsageService.try_increment_detail_calls', return_value=True),
            patch('line_bot.handlers.helpers.GoogleAPI.get_shop_detail') as mock_google,
        ):
            mock_google.return_value = {'name': '咖啡店'}
            info_d, cafe = get_or_create_cafe_info('some_place_id', user_id=1)

        assert info_d is None
        assert cafe is None

    def test_triggers_ai_summary_generation_when_new_cafe_has_reviews(self):
        """新建店家且 reviews 非空時，觸發 generate_cafe_ai_summary.delay"""
        user = UserFactory()
        place_id = 'test_place_id_with_reviews'
        google_data = {
            'place_id': place_id,
            'name': '測試咖啡店',
            'address': '台北市信義區',
            'lat': 25.033,
            'lng': 121.564,
            'reviews': ['環境安靜', '咖啡好喝'],
        }

        with (
            patch('line_bot.handlers.helpers.ApiUsageService.try_increment_detail_calls', return_value=True),
            patch('line_bot.handlers.helpers.GoogleAPI.get_shop_detail', return_value=google_data),
            patch('line_bot.handlers.helpers.CafeAttributeMatcher.match_and_sync_attributes', return_value=False),
            patch('line_bot.handlers.helpers.generate_cafe_ai_summary') as mock_summary_task,
        ):
            info_d, cafe = get_or_create_cafe_info(place_id, user.id)

        mock_summary_task.delay.assert_called_once_with(cafe.id)

    def test_does_not_trigger_ai_summary_generation_when_new_cafe_has_no_reviews(self):
        """新建店家且 reviews 為空時，不觸發 generate_cafe_ai_summary.delay"""
        user = UserFactory()
        place_id = 'test_place_id_without_reviews'
        google_data = {
            'place_id': place_id,
            'name': '測試咖啡店',
            'address': '台北市信義區',
            'lat': 25.033,
            'lng': 121.564,
            'reviews': [],
        }

        with (
            patch('line_bot.handlers.helpers.ApiUsageService.try_increment_detail_calls', return_value=True),
            patch('line_bot.handlers.helpers.GoogleAPI.get_shop_detail', return_value=google_data),
            patch('line_bot.handlers.helpers.CafeAttributeMatcher.match_and_sync_attributes', return_value=False),
            patch('line_bot.handlers.helpers.generate_cafe_ai_summary') as mock_summary_task,
        ):
            get_or_create_cafe_info(place_id, user.id)

        mock_summary_task.delay.assert_not_called()

    def test_does_not_trigger_ai_summary_generation_for_existing_cafe(self):
        """既有店家（非新建，直接從 DB 取得）不重複觸發 generate_cafe_ai_summary.delay"""
        cafe = CafeFactory(last_refreshed=timezone.now(), reviews=['環境安靜'])

        with (
            patch('line_bot.handlers.helpers.CafeAttributeMatcher.match_and_sync_attributes', return_value=False),
            patch('line_bot.handlers.helpers.generate_cafe_ai_summary') as mock_summary_task,
        ):
            get_or_create_cafe_info(cafe.place_id, user_id=1)

        mock_summary_task.delay.assert_not_called()


@pytest.mark.django_db
class TestGetOrCreateCafeInfoProtection:
    """新店建立的穿透與擊穿防護"""

    PLACE_ID = 'new_place_id'
    MODULE = 'line_bot.handlers.helpers'

    def _google_data(self, name='新咖啡店'):
        return {
            'place_id': self.PLACE_ID,
            'name': name,
            'address': '台北市信義區',
            'lat': 25.033,
            'lng': 121.564,
        }

    def _patches(self, google_return=None, google_side_effect=None):
        return (
            patch(f'{self.MODULE}.ApiUsageService.try_increment_detail_calls', return_value=True),
            patch(f'{self.MODULE}.GoogleAPI.get_shop_detail',
                  return_value=google_return, side_effect=google_side_effect),
            patch(f'{self.MODULE}.CafeAttributeMatcher.match_and_sync_attributes', return_value=False),
            patch(f'{self.MODULE}.refresh_cafe_if_stale', return_value=False),
        )

    def test_known_missing_place_skips_google_and_quota(self):
        """place_id 已確認無效：不扣額度、不呼叫 Google，回傳找不到"""
        user = UserFactory()
        increment, google, match, refresh = self._patches(google_return=self._google_data())

        with patch(f'{self.MODULE}.GoogleAPI.is_known_missing_place', return_value=True), \
             increment as mock_increment, google as mock_google, match, refresh:
            result = get_or_create_cafe_info(self.PLACE_ID, user.id)

        assert result == (None, None)
        mock_increment.assert_not_called()
        mock_google.assert_not_called()

    def test_creates_under_lock_named_by_place_id(self):
        """建立新店時以 place_id 加鎖"""
        user = UserFactory()
        increment, google, match, refresh = self._patches(google_return=self._google_data())

        with patch(f'{self.MODULE}.distributed_lock', wraps=distributed_lock) as mock_lock, \
             increment, google, match, refresh:
            get_or_create_cafe_info(self.PLACE_ID, user.id)

        mock_lock.assert_called_once_with(f'cafe:create:{self.PLACE_ID}', timeout=10)

    def test_lock_released_after_creation(self):
        """建立完成後鎖被釋放"""
        user = UserFactory()
        increment, google, match, refresh = self._patches(google_return=self._google_data())

        with increment, google, match, refresh:
            get_or_create_cafe_info(self.PLACE_ID, user.id)

        with distributed_lock(f'cafe:create:{self.PLACE_ID}') as acquired:
            assert acquired is True

    def test_existing_cafe_does_not_take_lock(self):
        """DB 已有店家時不加鎖"""
        user = UserFactory()
        cafe = CafeFactory(last_refreshed=timezone.now())
        increment, google, match, refresh = self._patches()

        with patch(f'{self.MODULE}.distributed_lock') as mock_lock, increment, google, match, refresh:
            get_or_create_cafe_info(cafe.place_id, user.id)

        mock_lock.assert_not_called()

    def test_double_check_after_acquiring_lock(self):
        """取得鎖時前一個持有者剛建立完成：直接回傳 DB 資料，不扣額度、不呼叫 Google"""
        user = UserFactory()
        increment, google, match, refresh = self._patches(google_return=self._google_data())

        @contextmanager
        def lock_after_other_holder_created(name, timeout=10):
            CafeFactory(place_id=self.PLACE_ID, name='別人建立的店')
            yield True

        with patch(f'{self.MODULE}.distributed_lock', side_effect=lock_after_other_holder_created), \
             increment as mock_increment, google as mock_google, match, refresh:
            info_d, cafe = get_or_create_cafe_info(self.PLACE_ID, user.id)

        assert info_d['name'] == '別人建立的店'
        assert cafe.place_id == self.PLACE_ID
        mock_increment.assert_not_called()
        mock_google.assert_not_called()

    def test_waits_for_holder_and_returns_created_cafe(self):
        """鎖被他人持有：等待 DB 出現該店後回傳，不扣額度、不呼叫 Google（防擊穿）"""
        user = UserFactory()
        increment, google, match, refresh = self._patches(google_return=self._google_data())
        polls = []

        def holder_creates_on_second_poll(_seconds):
            polls.append(_seconds)
            if len(polls) == 2:
                CafeFactory(place_id=self.PLACE_ID, name='持有者建立的店')

        with patch(f'{self.MODULE}.time.sleep', side_effect=holder_creates_on_second_poll), \
             increment as mock_increment, google as mock_google, match, refresh, \
             distributed_lock(f'cafe:create:{self.PLACE_ID}'):
            info_d, cafe = get_or_create_cafe_info(self.PLACE_ID, user.id)

        assert info_d['name'] == '持有者建立的店'
        assert len(polls) == 2
        mock_increment.assert_not_called()
        mock_google.assert_not_called()

    def test_wait_timeout_creates_itself(self, caplog):
        """等待逾時仍沒有該店：自行建立並記錄 warning（可用性優先）"""
        import logging
        user = UserFactory()
        increment, google, match, refresh = self._patches(google_return=self._google_data())

        with caplog.at_level(logging.WARNING), \
             patch(f'{self.MODULE}.time.sleep') as mock_sleep, \
             increment as mock_increment, google as mock_google, match, refresh, \
             distributed_lock(f'cafe:create:{self.PLACE_ID}'):
            info_d, cafe = get_or_create_cafe_info(self.PLACE_ID, user.id)

        assert mock_sleep.call_count == 20
        mock_increment.assert_called_once_with(user.id)
        mock_google.assert_called_once_with(self.PLACE_ID)
        assert info_d['name'] == '新咖啡店'
        assert Cafe.objects.filter(place_id=self.PLACE_ID).count() == 1
        assert self.PLACE_ID in caplog.text

    def test_integrity_error_returns_existing_cafe(self):
        """建立時撞到 place_id unique 限制：改讀既有資料，不回傳錯誤"""
        user = UserFactory()

        def other_process_creates_first(place_id):
            CafeFactory(place_id=self.PLACE_ID, name='另一個 process 建立的店')
            return self._google_data(name='我拿到的資料')

        increment, google, match, refresh = self._patches(google_side_effect=other_process_creates_first)

        with increment, google, match, refresh:
            info_d, cafe = get_or_create_cafe_info(self.PLACE_ID, user.id)

        assert info_d['name'] == '另一個 process 建立的店'
        assert cafe.place_id == self.PLACE_ID
        assert Cafe.objects.filter(place_id=self.PLACE_ID).count() == 1

    def test_google_failure_does_not_wait_for_db(self):
        """持有鎖且 Google 失敗：回傳找不到，鎖被釋放"""
        user = UserFactory()
        increment, google, match, refresh = self._patches(google_return={})

        with increment, google, match, refresh:
            result = get_or_create_cafe_info(self.PLACE_ID, user.id)

        assert result == (None, None)
        with distributed_lock(f'cafe:create:{self.PLACE_ID}') as acquired:
            assert acquired is True


class TestReplyText:
    """測試 reply_text"""

    def test_calls_api_with_correct_message(self):
        """正確呼叫 LINE API 傳送文字訊息"""
        mock_api = MagicMock()
        reply_text(mock_api, 'test_token', '測試訊息')

        mock_api.reply_message.assert_called_once()
        call_args = mock_api.reply_message.call_args[0][0]
        assert isinstance(call_args, ReplyMessageRequest)
        assert call_args.reply_token == 'test_token'
        assert isinstance(call_args.messages[0], TextMessage)
        assert call_args.messages[0].text == '測試訊息'


class TestReplyCafeDetail:
    """測試 reply_cafe_detail"""

    def test_sends_two_messages(self):
        """傳送 FlexMessage + 按鈕訊息共 2 則"""
        mock_api = MagicMock()
        info_d = {
            'place_id': 'test_place_id',
            'name': '測試咖啡店',
            'address': '台北市',
            'lat': 25.033,
            'lng': 121.564,
            'rating': 4.5,
        }

        with (
            patch('line_bot.builders.flex_builder.FlexMessageBuilder.create_shop_flex_message', return_value={}),
            patch('line_bot.builders.flex_builder.PostbackBuilder.create_cafe_action_postback') as mock_button,
            patch('line_bot.handlers.helpers.FlexContainer.from_json'),
            patch('line_bot.handlers.helpers.FlexMessage') as mock_flex_msg,
            patch('line_bot.handlers.helpers.ReplyMessageRequest') as mock_req,
        ):
            mock_button.return_value = MagicMock()
            mock_flex_msg.return_value = MagicMock()
            mock_req.return_value = MagicMock()
            reply_cafe_detail(mock_api, 'test_token', info_d)

        mock_api.reply_message.assert_called_once()
        messages = mock_req.call_args.kwargs['messages']
        assert len(messages) == 2

    def test_passes_is_favorited_to_postback_builder(self):
        """正確傳遞 is_favorited=True 給 PostbackBuilder"""
        mock_api = MagicMock()
        info_d = {'place_id': 'test_place_id', 'name': '測試咖啡店'}

        with (
            patch('line_bot.builders.flex_builder.FlexMessageBuilder.create_shop_flex_message', return_value={}),
            patch('line_bot.builders.flex_builder.PostbackBuilder.create_cafe_action_postback') as mock_button,
            patch('line_bot.handlers.helpers.FlexContainer.from_json'),
            patch('line_bot.handlers.helpers.FlexMessage'),
            patch('line_bot.handlers.helpers.ReplyMessageRequest'),
        ):
            mock_button.return_value = MagicMock()
            reply_cafe_detail(mock_api, 'test_token', info_d, is_favorited=True)

        mock_button.assert_called_once_with(info_d=info_d, is_favorited=True)
