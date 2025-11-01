# Create your views here.
import json
import logging
import os

import certifi
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt

from line_bot.utils import GoogleAPI, FlexMessageBuilder

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
    ButtonsTemplate,
    PostbackAction,
    TemplateMessage,
    Emoji,
    VideoMessage,
    LocationMessage,
    LocationAction,
    StickerMessage,
    ImageMessage,
    FlexBubble,
    FlexMessage,
    FlexImage,
    FlexBox,
    FlexText,
    FlexIcon,
    FlexButton,
    FlexSeparator,
    FlexContainer,
    QuickReply,
    QuickReplyItem,
    LocationAction,
    MessagingApiBlob,
    RichMenuArea,
    RichMenuBounds,
    RichMenuSize,
    RichMenuRequest,
    MessageAction

)
from linebot.v3.webhooks import (
    MessageEvent,
    FollowEvent,
    TextMessageContent,
    PostbackEvent,
    LocationMessageContent

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
    print('加入')


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        text = event.message.text

        if text == 'postback':
            button_template = ButtonsTemplate(
                titile='嗨',
                text='postback action',
                actions=[
                    PostbackAction(label='Postback action', text='postback action button clicked', data='postback')
                ])
            template_message = TemplateMessage(
                alt_text='postback action',
                template=button_template,
            )
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[template_message]
                )
            )

        elif text == '貼圖':
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[StickerMessage(package_id='446', sticker_id='1998')]
                )
            )

        elif text == '表情符號':
            emojis = [
                Emoji(index=0, product_id='5ac1bfd5040ab15980c9b435', emoji_id='001'),
                Emoji(index=6, product_id='5ac1bfd5040ab15980c9b435', emoji_id='002')
            ]
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text='$LINE~$ 表情', emojis=emojis)]
                )
            )

        elif text == '圖片':
            url = os.getenv('image_url')
            logger.info("Image URL: " + url)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[ImageMessage(original_content_url=url, preview_image_url=url)]
                )
            )
        elif text == '位置':
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[LocationMessage(title='台北101', address='台北市信義路五段7號', latitude=25.033611,
                                              longitude=121.565000)]
                )
            )
        # 251026 先寫死
        if text.startswith('分享位置'):
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

        # 251024 先寫死
        if text.startswith('新北市板橋區'):
            shops = GoogleAPI.search_nearby_coffee_shops(address=text)

            if not shops:
                line_bot_api.reply_message_with_http_info(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=f'抱歉，找不到{text}附近的咖啡店喔！')]
                    )
                )

            else:
                flex_messages = []
                for shop in shops:
                    place_id = shop[0]
                    info_d = GoogleAPI.get_shop_detail(place_id)

                    if info_d:
                        flex_content = FlexMessageBuilder.create_shop_flex_message(info_d, is_multiple=True)
                        flex_messages.append(flex_content)

                if flex_messages:
                    carousel = {
                        "type": "carousel",
                        "contents": flex_messages
                    }

                    line_bot_api.reply_message_with_http_info(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[FlexMessage(
                                alt_text=f"找到 {len(flex_messages)} 間咖啡店",
                                contents=FlexContainer.from_dict(carousel)
                            )]
                        )
                    )

                else:
                    line_bot_api.reply_message_with_http_info(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text="無法取得店家詳細資訊")]
                        )
                    )


        else:
            shops = GoogleAPI.search_coffee_shops(text)

            if len(shops) == 1:
                place_id = shops[0]['place_id']
                info_d = GoogleAPI.get_shop_detail(place_id)
                flex_data = FlexMessageBuilder.create_shop_flex_message(info_d)

                # 轉成 JSON 給 FlexContainer
                flex_container = FlexContainer.from_json(json.dumps(flex_data))

                # 回覆
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[
                            FlexMessage(
                                alt_text='找到咖啡店囉，快來看看吧！',
                                contents=flex_container
                            )
                        ]
                    )
                )


            # 搜尋結果 介於2 ~5 筆
            elif 2 <= len(shops) <= 5:
                flex_messages = []
                for shop in shops:
                    place_id = shop.get('place_id')
                    info_d = GoogleAPI.get_shop_detail(place_id)

                    if info_d:
                        flex_content = FlexMessageBuilder.create_shop_flex_message(info_d, is_multiple=True)
                        flex_messages.append(flex_content)

                if flex_messages:
                    carousel = {
                        "type": "carousel",
                        "contents": flex_messages
                    }

                    line_bot_api.reply_message_with_http_info(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[FlexMessage(
                                alt_text=f"找到 {len(flex_messages)} 間咖啡店",
                                contents=FlexContainer.from_dict(carousel)
                            )]
                        )
                    )

                else:
                    line_bot_api.reply_message_with_http_info(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text="無法取得店家詳細資訊")]
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

        flex_messages = []
        for shop in shops:
            place_id = shop[0]
            logger.info(place_id)
            info_d = GoogleAPI.get_shop_detail(place_id)
            logger.info(info_d)

            if info_d:
                flex_content = FlexMessageBuilder.create_shop_flex_message(info_d, is_multiple=True)
                flex_messages.append(flex_content)

        if flex_messages:
            carousel = {
                "type": "carousel",
                "contents": flex_messages
            }

            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[FlexMessage(
                        alt_text=f"找到 {len(flex_messages)} 間咖啡店",
                        contents=FlexContainer.from_dict(carousel)
                    )]
                )
            )

        else:
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="無法取得店家詳細資訊")]
                )
            )


def rich_menu():
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_blob_aoi = MessagingApiBlob(api_client)

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
                        label='首頁',
                        text='首頁'
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
                        label='產品介紹',
                        text='產品介紹'
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
                        label='最新消息',
                        text='最新消息'
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
                        label='聯絡我們',
                        text='聯絡我們'
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
                        label='關於我們',
                        text='關於我們'
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
                        label='常見問題',
                        text='常見問題'
                    )
                )
            ]
        )

        rich_menu_id = line_bot_api.create_rich_menu(
            rich_menu_request=rich_menu_create
        ).rich_menu_id

        with open('static/images/rich_menu_image.jpg', 'rb') as image:
            line_bot_blob_aoi.set_rich_menu_image(
                rich_menu_id=rich_menu_id,
                _headers={'Content-Type': 'image/jpeg'},
                body=bytearray(image.read())
            )

        line_bot_api.set_default_rich_menu(
            rich_menu_id=rich_menu_id
        )
        rich_menu_response = line_bot_api.create_rich_menu(rich_menu_request=rich_menu_create)
        print("Rich menu ID:", rich_menu_response.rich_menu_id)
