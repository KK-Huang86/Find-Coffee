import json
import logging
from decouple import config

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
from users.models import User
from cafe.models import Cafe
from users.views import FavoritesManager

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

        if state == UserState.NORMAL:
            pass

        # 使用者查詢單一咖啡店，回傳結果
        if state == UserState.WAITING_SHOP_NAME:
            shops = GoogleAPI.search_coffee_shops(text)
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
        if state == UserState.WAITING_ADDRESS:
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
                message = TextMessage(
                    text='您還沒有收藏任何咖啡店喔～\n快去探索喜歡的店家吧！❤️',
                )

            elif favorite_count <= 5:
                # 1-5 間 → Carousel
                message = FavoritesMessageBuilder.show_favorites_carousel(user_id)

            else:
                # 超過 5 間 → 分多頁的 Carousel
                message = FavoritesMessageBuilder.show_favorites_list(user_id)

            message.quick_reply =  QuickReplyBuilder.create_favorites_actions()

            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[message]
                )
            )

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
        user = User.objects.filter(line_user_id=user_id)

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


# postback 處理
@handler.add(PostbackEvent)
def handle_postback(event):
    """
    postback 統一格式為 action=XXXXl(view_detail、favorite)&place_id={XXXXX}
    """
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        data = event.postback.data  # ex: favorite&pid=xxxxx

        # e.g {'action': 'view_detail', 'place_id': 'ChIJXdYuc5qpQjQReM1zieXbGeA'}
        params = dict(
            item.split('=') for item in data.split('&')
            if '=' in item
        )

        user_id = event.source.user_id
        user = User.objects.filter(line_user_id=user_id).first()

        if not user:
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text='找不到會員資料，請重新操作')]
                )
            )
            return

        action = params.get('action')
        place_id = params.get('place_id')

        # ⭐ 收藏
        if action == 'favorite':

            cafe = Cafe.objects.filter(place_id=place_id).first()
            if cafe:

                info_d = cafe.to_dict()
            else:
                info_d = GoogleAPI.get_shop_detail(place_id)

            ok, msg = FavoritesManager.add_favorite(user, info_d)

            reply = TextMessage(text=msg)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[reply]
                )
            )
            return

        if action == 'unfavorite':
            cafe = Cafe.objects.filter(place_id=place_id).first()
            if cafe:
                info_d = cafe.to_dict()

            else:
                reply = TextMessage(text='找不到該咖啡店，無法取消收藏')
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[reply]
                    )
                )
                return

            ok, msg = FavoritesManager.remove_favorite(user, info_d)

            reply = TextMessage(text=msg)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[reply]
                )
            )
            return

        if action == 'view_detail':
            is_favorited = False
            cafe = Cafe.objects.filter(place_id=place_id).first()

            # 1. 取得店家資訊
            if cafe:
                info_d = cafe.to_dict()
                is_favorited = user.favorites.filter(cafe=cafe).exists()
            else:
                info_d = GoogleAPI.get_shop_detail(place_id)
                if not info_d:
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text='找不到此咖啡店')]
                        )
                    )
                    return

            # 2. 建立 Flex Message（統一在這裡）
            flex_data = FlexMessageBuilder.create_shop_flex_message(info_d)
            flex_container = FlexContainer.from_json(json.dumps(flex_data))

            # 3. 建立按鈕
            button_message = PostbackBuilder.create_cafe_action_postback(
                info_d=info_d,
                is_favorited=is_favorited
            )

            # 4. 回覆
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[
                        FlexMessage(
                            alt_text='咖啡店詳細資訊',
                            contents=flex_container
                        ),
                        button_message
                    ]
                )
            )
            return
