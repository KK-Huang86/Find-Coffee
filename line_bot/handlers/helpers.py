"""
通用 Helper 函數 - 減少 postback handlers 中的重複程式碼
"""
import json

from linebot.v3.messaging import (
    ReplyMessageRequest,
    TextMessage,
    FlexMessage,
    FlexContainer,
)

from cafe.models import Cafe
from integrations.google.api import GoogleAPI
from line_bot.builders.flex_builder import FlexMessageBuilder, PostbackBuilder


def get_cafe_info(place_id):
    """
    從 DB 或 Google API 取得咖啡店資訊

    Returns:
        tuple: (info_dict, cafe_object)
               若找不到則 info_dict 為 None
    """
    cafe = Cafe.objects.filter(place_id=place_id).first()
    if cafe:
        return cafe.to_dict(), cafe
    info_d = GoogleAPI.get_shop_detail(place_id)
    return info_d, None


def reply_text(line_bot_api, reply_token, text):
    """簡單文字回覆"""
    line_bot_api.reply_message(
        ReplyMessageRequest(
            reply_token=reply_token,
            messages=[TextMessage(text=text)]
        )
    )


def reply_cafe_detail(line_bot_api, reply_token, info_d, is_favorited=False):
    """
    回覆咖啡店詳細資訊 (Flex Message + 操作按鈕)
    """
    flex_data = FlexMessageBuilder.create_shop_flex_message(info_d)
    flex_container = FlexContainer.from_json(json.dumps(flex_data))

    button_message = PostbackBuilder.create_cafe_action_postback(
        info_d=info_d,
        is_favorited=is_favorited
    )

    line_bot_api.reply_message(
        ReplyMessageRequest(
            reply_token=reply_token,
            messages=[
                FlexMessage(
                    alt_text='咖啡店詳細資訊',
                    contents=flex_container
                ),
                button_message
            ]
        )
    )
