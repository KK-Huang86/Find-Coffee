# Create your views here.
import logging
import os

import certifi
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt

from line_bot.models import User
from line_bot.utils import GoogleAPI, LineMessageBuilder, FavoritesManager

# 設定 SSL 憑證路徑
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    QuickReply,
    QuickReplyItem,
    LocationAction,
    MessagingApiBlob,
    RichMenuArea,
    RichMenuBounds,
    RichMenuSize,
    RichMenuRequest,
    MessageAction,

)
from linebot.v3.webhooks import (
    MessageEvent,
    FollowEvent,
    TextMessageContent,
    LocationMessageContent,
    PostbackEvent

)

logger = logging.getLogger(__name__)

# 初始化設定
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)


@csrf_exempt
def callback(request):
    if request.method != 'POST':
        return HttpResponseBadRequest()

    # 取得 X-Line-Signature header 值
    signature = request.headers.get('X-Line-Signature', '')

    # 取得 request body
    body = request.body.decode('utf-8')
    logger.info('Request body: ' + body)

    # 處理 webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error('Invalid signature. Please check your channel access token/channel secret.')
        return HttpResponseBadRequest()

    return HttpResponse('OK')


@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    User.objects.get_or_create(line_user_id=user_id)


user_states = {}


class UserState:
    NORMAL = 'normal'
    WAITING_SHOP_NAME = 'waiting_shop_name'
    WAITING_ADDRESS = 'waiting_address'


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        user_id = event.source.user_id
        text = event.message.text
        state = user_states.get(user_id, UserState.NORMAL)

        if state == UserState.NORMAL:
            pass

        if state == UserState.WAITING_SHOP_NAME:
            shops = GoogleAPI.search_coffee_shops(text)
            LineMessageBuilder.send_shop_result(line_bot_api, event.reply_token, shops)
            user_states[user_id] = UserState.NORMAL
            return

        if state == UserState.WAITING_ADDRESS:
            shops = GoogleAPI.search_nearby_coffee_shops(address=text)
            LineMessageBuilder.send_shop_result(line_bot_api, event.reply_token, shops)
            user_states[user_id] = UserState.NORMAL
            return

        if text == '分享位置查詢':

            quick_reply = QuickReply(
                items=[
                    QuickReplyItem(
                        action=LocationAction(
                            label='📍 分享目前位置'
                        )
                    )
                ]
            )

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

        elif text == '路名查詢':
            user_states[user_id] = UserState.WAITING_ADDRESS
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text='請輸入路名️（例如：台北市信義區松信路）')]
                )
            )
            return

        elif text == '店名查詢':
            user_states[user_id] = UserState.WAITING_SHOP_NAME
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text='請輸入咖啡店名稱 ☕️')]
                )
            )
            return

        elif text =='收藏的咖啡店':
            user = User.objects.get(line_user_id=user_id)
            favorite_count = user.favorites.count()

            if favorite_count == 0:
                # 沒有收藏
                message = TextMessage(text='您還沒有收藏任何咖啡店喔～\n快去探索喜歡的店家吧！❤️')

            elif favorite_count <= 5:
                # 1-5 間 → Carousel
                message = FavoritesManager.show_favorites_carousel(user_id, event)

            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[message]
                )
            )

        else: # 待改
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text='請使用選單功能來查詢咖啡店 ☕️')]
                )
            )


@handler.add(MessageEvent, message=LocationMessageContent)
def handle_location_message(event):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        lat = event.message.latitude
        lng = event.message.longitude
        address = event.message.address  # 可能為 None

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

        LineMessageBuilder.send_shop_result(line_bot_api, event.reply_token, shops)


@handler.add(PostbackEvent)
def handle_postback(event):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        data = event.postback.data  # ex: favorite&pid=xxxxx

        params = dict(
            item.split("=") for item in data.split("&")
            if "=" in item
        )


        user_id = event.source.user_id
        user = User.objects.filter(line_user_id=user_id).first()

        # ⭐ 收藏
        if data.startswith('favorite'):
            place_id = params.get('pid')
            info = GoogleAPI.get_shop_detail(place_id)
            ok, msg = FavoritesManager.add_favorite(user, info)

            reply = TextMessage(text=msg)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[reply]
                )
            )
            return


def rich_menu():
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_blob_api = MessagingApiBlob(api_client)

        rich_menu_create = RichMenuRequest(
            size=RichMenuSize(
                width=2500,
                height=1686
            ),
            selected=True,
            name='Nice richmenu',
            chat_bar_text='點我查看更多',
            areas=[
                RichMenuArea(
                    bounds=RichMenuBounds(
                        x=0,
                        y=0,
                        width=833,
                        height=843
                    ),
                    action=MessageAction(
                        label='店名查詢',
                        text='店名查詢'
                    )
                ),
                RichMenuArea(
                    bounds=RichMenuBounds(
                        x=834,
                        y=0,
                        width=833,
                        height=843
                    ),
                    action=MessageAction(
                        label='路名查詢',
                        text='路名查詢'
                    )
                ),
                RichMenuArea(
                    bounds=RichMenuBounds(
                        x=1666,
                        y=0,
                        width=834,
                        height=843
                    ),
                    action=MessageAction(
                        label='分享位置查詢',
                        text='分享位置查詢'
                    )
                ),
                RichMenuArea(
                    bounds=RichMenuBounds(
                        x=0,
                        y=844,
                        width=833,
                        height=842
                    ),
                    action=MessageAction(
                        label='收藏的咖啡店',
                        text='收藏的咖啡店'
                    )
                ),
                RichMenuArea(
                    bounds=RichMenuBounds(
                        x=834,
                        y=844,
                        width=833,
                        height=842
                    ),
                    action=MessageAction(
                        label='最近查詢',
                        text='最近查詢'
                    )
                ),
                RichMenuArea(
                    bounds=RichMenuBounds(
                        x=1666,
                        y=844,
                        width=834,
                        height=842
                    ),
                    action=MessageAction(
                        label='更多資訊',
                        text='更多資訊'
                    )
                )
            ]
        )

        rich_menu_id = line_bot_api.create_rich_menu(
            rich_menu_request=rich_menu_create
        ).rich_menu_id

        with open('static/rich_menu.png', 'rb') as image:
            line_bot_blob_api.set_rich_menu_image(
                rich_menu_id=rich_menu_id,
                _headers={'Content-Type': 'image/jpeg'},
                body=bytearray(image.read())
            )

        line_bot_api.set_default_rich_menu(
            rich_menu_id=rich_menu_id
        )


rich_menu()
