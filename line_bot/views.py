# Create your views here.
import logging
import os
from decouple import config

import certifi
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt

# 設定 SSL 憑證路徑
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    MessagingApiBlob,
    RichMenuArea,
    RichMenuBounds,
    RichMenuSize,
    RichMenuRequest,
    PostbackAction,
)

from .event_handlers import handler
from .constants import MenuText, MenuAction

logger = logging.getLogger(__name__)

# 初始化設定
LINE_CHANNEL_ACCESS_TOKEN = config('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = config('LINE_CHANNEL_SECRET')

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)


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
            name='richmenu',
            chat_bar_text='點我查看更多',
            areas=[
                RichMenuArea(
                    bounds=RichMenuBounds(x=0, y=0, width=833, height=843),
                    action=PostbackAction(
                        label=MenuText.SEARCH_SHOP_NAME,
                        data=f'action=menu&type={MenuAction.SEARCH_SHOP_NAME}'
                    )
                ),
                RichMenuArea(
                    bounds=RichMenuBounds(x=834, y=0, width=833, height=843),
                    action=PostbackAction(
                        label=MenuText.SEARCH_ADDRESS,
                        data=f'action=menu&type={MenuAction.SEARCH_ADDRESS}'
                    )
                ),
                RichMenuArea(
                    bounds=RichMenuBounds(x=1666, y=0, width=834, height=843),
                    action=PostbackAction(
                        label=MenuText.SHARE_LOCATION,
                        data=f'action=menu&type={MenuAction.SHARE_LOCATION}'
                    )
                ),
                RichMenuArea(
                    bounds=RichMenuBounds(x=0, y=844, width=833, height=842),
                    action=PostbackAction(
                        label=MenuText.FAVORITES,
                        data=f'action=menu&type={MenuAction.FAVORITES}'
                    )
                ),
                RichMenuArea(
                    bounds=RichMenuBounds(x=834, y=844, width=833, height=842),
                    action=PostbackAction(
                        label=MenuText.RECENT_SEARCH,
                        data=f'action=menu&type={MenuAction.RECENT_SEARCH}'
                    )
                ),
                RichMenuArea(
                    bounds=RichMenuBounds(x=1666, y=844, width=834, height=842),
                    action=PostbackAction(
                        label=MenuText.MORE_INFO,
                        data=f'action=menu&type={MenuAction.MORE_INFO}'
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


# rich_menu()  # 需要時手動呼叫，不要自動執行
