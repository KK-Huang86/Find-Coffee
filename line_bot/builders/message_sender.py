import json
import logging

from linebot.v3.messaging import (
    ReplyMessageRequest,
    TextMessage,
    FlexContainer,
    FlexMessage,
)

from line_bot.constants import QUOTA_EXCEEDED
from line_bot.builders.shop_flex_message import FlexMessageBuilder
from line_bot.builders.postback import PostbackBuilder

from cafe.models import Cafe

logger = logging.getLogger(__name__)


class LineMessageBuilder:

    @staticmethod
    def _get_or_create_shop_info(place_id, user_id):
        """
        嘗試從資料庫取得店家資訊，若無，則從 Google API 取得資料並寫入資料庫。
        委託給 helpers.get_or_create_cafe_info 統一處理。
        """
        from line_bot.handlers.helpers import get_or_create_cafe_info
        return get_or_create_cafe_info(place_id, user_id)

    @staticmethod
    def send_shop_result(line_bot_api, reply_token, shops, user, quick_reply=None):

        if not shops:
            logger.error('找不到店家資訊')
            # 回傳找不到店家的訊息
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text='無法取得店家詳細資訊')]
                )
            )
            return

        if len(shops) == 1:
            # 單筆結果：才需要取得完整詳細資訊
            place_id = shops[0]['place_id']

            info_d, cafe = LineMessageBuilder._get_or_create_shop_info(place_id, user.id)

            if info_d is QUOTA_EXCEEDED:
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[TextMessage(text='本月 API 查詢額度已達上限，無法取得店家資訊 😢')]
                    )
                )
                return
            if not info_d:
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[TextMessage(text='無法取得店家詳細資訊')]
                    )
                )
                return

            is_favorited = user.favorites.filter(cafe=cafe).exists()

            flex_data = FlexMessageBuilder.create_shop_flex_message(info_d)

            # 轉成 JSON 給 FlexContainer
            flex_container = FlexContainer.from_json(json.dumps(flex_data))

            # postback
            button_message = PostbackBuilder.create_cafe_action_postback(
                info_d,
                is_favorited=is_favorited
            )

            button_message.quick_reply = quick_reply

            # 回覆
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[
                        FlexMessage(
                            alt_text='找到咖啡店囉，快來看看吧！',
                            contents=flex_container
                        ),
                        button_message
                    ]
                )
            )
            return

        if 2 <= len(shops) <= 10:
            # 多筆結果：先批次查 DB，減少 Google API 呼叫次數
            place_ids = [shop['place_id'] for shop in shops]
            cached_cafes = {
                cafe.place_id: cafe.to_dict()
                for cafe in Cafe.objects.filter(place_id__in=place_ids)
            }

            flex_messages = []
            for shop in shops:
                place_id = shop['place_id']

                if place_id in cached_cafes:
                    info_d = cached_cafes[place_id]
                else:
                    info_d, _ = LineMessageBuilder._get_or_create_shop_info(place_id, user.id)

                if info_d is QUOTA_EXCEEDED:
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=reply_token,
                            messages=[TextMessage(text='本月 API 查詢額度已達上限，無法取得店家資訊 😢')]
                        )
                    )
                    return
                if info_d:
                    flex_data = FlexMessageBuilder.create_shop_flex_message(info_d, is_multiple=True)
                    flex_messages.append(flex_data)

                else:
                    logger.warning(f'無法取得店家詳細資訊，place_id: {place_id}')
                    continue

            if flex_messages:
                carousel = {
                    'type': 'carousel',
                    'contents': flex_messages
                }

                flex_message = FlexMessage(
                    alt_text=f'找到 {len(flex_messages)} 間咖啡店',
                    contents=FlexContainer.from_dict(carousel)
                )

                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[
                            TextMessage(text=f'找到 {len(flex_messages)} 間咖啡店，為你列出結果 ☕'),
                            flex_message,
                            TextMessage(text='今天想選擇哪一間咖啡店呢？', quick_reply=quick_reply)
                        ]
                    )
                )

            else:
                line_bot_api.reply_message_with_http_info(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[TextMessage(text='無法取得店家詳細資訊')]
                    )
                )
