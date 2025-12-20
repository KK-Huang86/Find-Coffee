import json
import logging

from linebot.v3.messaging import (
    ReplyMessageRequest,
    TextMessage,
    FlexMessage,
    FlexContainer,
)

from cafe.models import Cafe
from integrations.google.api import GoogleAPI
from line_bot.utils import parse_opening_hours

logger = logging.getLogger(__name__)


def get_or_create_cafe_info(place_id):
    """
    從 DB 取得咖啡店資訊，若無則從 Google API 取得並存入 DB。

    Args:
        place_id (str): Google Places ID

    Returns:
        tuple: (info_dict, cafe_object)
               若失敗則回傳 (None, None)
    """
    # 1. 先查 DB
    cafe = Cafe.objects.filter(place_id=place_id).first()
    if cafe:
        return cafe.to_dict(), cafe

    # 2. DB 沒有，呼叫 Google API
    info_d = GoogleAPI.get_shop_detail(place_id)

    if not info_d:
        return None, None

    if not info_d.get('place_id'):
        logger.error('缺少 place_id，無法建立店家資料')
        return None, None

    # 3. 存入 DB
    try:
        opening_hours_l = info_d.get('opening_hours', [])
        opening_hours_d = parse_opening_hours(opening_hours_l)

        cafe = Cafe.objects.create(
            place_id=info_d['place_id'],
            name=info_d.get('name') or '未提供名稱',
            address=info_d.get('address') or '未提供地址',
            phone=info_d.get('phone') or '未提供電話',
            rating=info_d.get('rating'),
            user_ratings_total=info_d.get('user_ratings_total', 0),
            google_maps=info_d.get('google_maps') or '',
            website=info_d.get('website') or '',
            lat=info_d.get('lat') or 0.0,
            lng=info_d.get('lng') or 0.0,
            opening_hours=opening_hours_d
        )
        logger.info(f'建立新咖啡店: {cafe.name} ({cafe.place_id})')
        return cafe.to_dict(), cafe

    except Exception as e:
        logger.error(f'儲存店家資料時發生錯誤: {e}', exc_info=True)
        return None, None


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
    # 延遲導入避免循環引用
    from line_bot.builders.flex_builder import FlexMessageBuilder, PostbackBuilder

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
