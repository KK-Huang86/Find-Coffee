import json
import logging
from decouple import config
from urllib.parse import parse_qs


from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    QuickReply,
    QuickReplyItem,
    LocationAction,
    FlexMessage,
    FlexContainer

)
from linebot.v3.webhooks import (
    MessageEvent,
    FollowEvent,
    TextMessageContent,
    LocationMessageContent,
    PostbackEvent

)

from integrations.google.api import GoogleAPI
from line_bot.constants import UserState, MenuText
from line_bot.builders.flex_builder import LineMessageBuilder, FlexMessageBuilder, PostbackBuilder, \
    FavoritesMessageBuilder, QuickReplyBuilder
from line_bot.handlers.postback_actions import ACTION_HANDLERS
from line_bot.handlers.helpers import reply_text
from line_bot.services.search_cache import SearchHistoryService
from users.models import User
from cafe.models import Cafe
from users.views import FavoritesManager
from utils.utils import LockService

logger = logging.getLogger(__name__)
LINE_CHANNEL_ACCESS_TOKEN = config('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = config('LINE_CHANNEL_SECRET')

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)


# 使用者追蹤機器人時，建立使用者資料
@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    User.objects.get_or_create(line_user_id=user_id)


user_states = {}


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        user_id = event.source.user_id
        text = event.message.text
        state = user_states.get(user_id, UserState.NORMAL)
        user = User.objects.get(line_user_id=user_id)

        if not LockService.acquire(user_id, 'message'):
            logger.info(f'User {user_id} throttled, skip processing')
            return

        # 使用者查詢單一咖啡店，回傳結果
        if state == UserState.WAITING_SHOP_NAME:
            # 1. 先查本地 DB
            cached_cafes = Cafe.objects.filter(name__icontains=text)[:5]

            if cached_cafes.exists():
                # 本地有資料，直接使用
                # TODO 後續會加異步檢查 last_refreshed
                shops = [{'place_id': cafe.place_id} for cafe in cached_cafes]
            else:
                # 本地沒有，打 Google API
                shops = GoogleAPI.search_coffee_shops(text)

            # 紀錄搜尋歷史
            SearchHistoryService.add_search(user_id, text, search_type='shop_name')

            LineMessageBuilder.send_shop_result(
                line_bot_api,
                event.reply_token,
                shops,
                user,
                quick_reply=QuickReplyBuilder.create_search_again_actions()
            )
            user_states[user_id] = UserState.NORMAL
            return

        # 使用者查詢某一路名的咖啡店，回傳結果
        elif state == UserState.WAITING_ADDRESS:

            # 紀錄 Cache
            SearchHistoryService.add_search(user_id, text, search_type='address')

            shops = GoogleAPI.search_nearby_coffee_shops(address=text)
            LineMessageBuilder.send_shop_result(
                line_bot_api,
                event.reply_token,
                shops,
                user,
                quick_reply=QuickReplyBuilder.create_carousel_pagination_actions()
            )
            user_states[user_id] = UserState.NORMAL
            return

        # 使用者開始定位分享查詢咖啡店
        elif text == MenuText.SHARE_LOCATION:

            quick_reply = QuickReplyBuilder.create_location_request()

            # 回覆訊息
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[
                        TextMessage(
                            text=(
                                '請點擊下方按鈕分享您的位置\n'
                                '我來幫您找附近的咖啡店 ☕️'
                            ),
                            quick_reply=quick_reply
                        )
                    ]
                )
            )

        # 使用者點選查詢路名
        elif text == MenuText.SEARCH_ADDRESS:
            user_states[user_id] = UserState.WAITING_ADDRESS
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text='請輸入路名️（例如：台北市信義區松信路）')]
                )
            )
            return

        # 使用者點選查詢咖啡店
        elif text == MenuText.SEARCH_SHOP_NAME:
            user_states[user_id] = UserState.WAITING_SHOP_NAME
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text='請輸入咖啡店名稱 ☕️')]
                )
            )
            return

        # 使用者點選查詢收藏名單
        elif text == MenuText.FAVORITES:
            user = User.objects.get(line_user_id=user_id)
            favorite_count = user.favorites.count()

            if favorite_count == 0:
                # 沒有收藏
                message = TextMessage(text='您還沒有收藏任何咖啡店喔～\n快去探索喜歡的店家吧！❤️')

            elif favorite_count <= 5:
                # 1-5 間 → Carousel
                message = FavoritesMessageBuilder.show_favorites_carousel(user_id)

            else:
                # 超過 5 間 → 分多頁的 Carousel
                message = FavoritesMessageBuilder.show_favorites_list(user_id)

            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[message]
                )
            )
        elif text == MenuText.RECENT_SEARCH:
            quick_reply = QuickReplyBuilder.create_recent_search_quick_reply(user_id)

            if quick_reply:
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[
                            TextMessage(
                                text='請選擇最近搜尋的關鍵字：',
                                quick_reply=quick_reply
                            )
                        ]
                    )
                )
            else:
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text='目前還沒有搜尋紀錄喔～')]
                    )
                )
            return

        # 使用者並沒有先點 RichMenu而輸入文字
        else:  # 待改
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text='請使用選單功能來查詢咖啡店 ☕️')]
                )
            )


# 分享位置查詢
@handler.add(MessageEvent, message=LocationMessageContent)
def handle_location_message(event):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        lat = event.message.latitude
        lng = event.message.longitude
        address = event.message.address  # 可能為 None

        user_id = event.source.user_id
        user = User.objects.filter(line_user_id=user_id).first()

        if not user:
            logger.warning(f'User not found: {user_id}')
            reply_text(line_bot_api, event.reply_token, '找不到會員資料，請重新操作')
            return

        if not LockService.acquire(user_id, 'location'):
            logger.info(f'User {user_id} throttled, skip processing')
            return

        shops = GoogleAPI.search_nearby_coffee_shops(lat=lat, lng=lng)
        logger.info(shops)

        if not shops:
            logger.warning('️沒有找到任何咖啡店')
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[
                        TextMessage(
                            text=(
                                '附近 500 公尺內找不到咖啡店 😢\n\n'
                                '試試看：\n'
                                '1️⃣ 分享其他位置\n'
                                '2️⃣ 輸入地址搜尋'
                            )
                        )
                    ]
                )
            )
            return

        LineMessageBuilder.send_shop_result(line_bot_api, event.reply_token, shops, user)


def _parse_postback_data(data: str) -> dict:
    parsed = parse_qs(data)
    return {k: v[0] for k, v in parsed.items()}

# postback 處理
@handler.add(PostbackEvent)
def handle_postback(event):
    """
    postback 統一格式為 action=XXX&param1=XXX&param2=XXX
    使用 ACTION_HANDLERS dispatch table 路由到對應的 handler
    """
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        data = event.postback.data

        # 解析 postback data
        params = _parse_postback_data(data)

        user_id = event.source.user_id
        user = User.objects.filter(line_user_id=user_id).first()

        if not user:
            logger.warning(f'User not found: {user_id}')
            reply_text(line_bot_api, event.reply_token, '找不到會員資料，請重新操作')
            return

        if not LockService.acquire(user_id, 'postback'):
            logger.info(f'User {user_id} throttled, skip processing')
            return

        if not user:
            reply_text(line_bot_api, event.reply_token, '找不到會員資料，請重新操作')
            return

        action = params.get('action')
        handler_func = ACTION_HANDLERS.get(action)

        if handler_func:
            handler_func(line_bot_api, event.reply_token, user, params)
        else:
            logger.warning(f'Unknown postback action: {action}')
