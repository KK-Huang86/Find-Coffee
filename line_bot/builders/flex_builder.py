import json
import logging

from linebot.v3.messaging import (
    ReplyMessageRequest,
    TextMessage,
    FlexContainer,
    FlexMessage,
    FlexBubble,
)

from line_bot.constants import QUOTA_EXCEEDED
from line_bot.builders.postback import PostbackBuilder
from line_bot.builders.shop_flex_message import FlexMessageBuilder

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


class FavoritesPageBuilder:

    @staticmethod
    def build_page_message(favorites, page_num=1):
        """
        以列表 bubble 呈現一頁收藏（最多 15 筆）。
        每一列可點擊，觸發 view_detail postback。
        """
        title = '❤️ 我的收藏' if page_num == 1 else f'❤️ 我的收藏（第 {page_num} 頁）'

        contents = [
            {'type': 'text', 'text': title, 'weight': 'bold', 'size': 'xl', 'margin': 'md'},
            {'type': 'separator', 'margin': 'lg'},
        ]

        for i, fav in enumerate(favorites, 1):
            today_hours = FlexMessageBuilder.format_opening_hours(fav.cafe.opening_hours)
            shop_box = {
                'type': 'box',
                'layout': 'vertical',
                'margin': 'lg',
                'spacing': 'xs',
                'contents': [
                    {
                        'type': 'box',
                        'layout': 'baseline',
                        'spacing': 'sm',
                        'contents': [
                            {
                                'type': 'text',
                                'text': f'{i}.',
                                'size': 'sm',
                                'color': '#aaaaaa',
                                'flex': 0,
                            },
                            {
                                'type': 'text',
                                'text': fav.cafe.name,
                                'weight': 'bold',
                                'size': 'sm',
                                'wrap': True,
                                'flex': 1,
                            },
                        ]
                    },
                    {
                        'type': 'text',
                        'text': fav.cafe.address or '',
                        'size': 'xs',
                        'color': '#aaaaaa',
                        'wrap': True,
                    },
                    {
                        'type': 'text',
                        'text': f'⭐ {fav.cafe.rating if fav.cafe.rating is not None else "N/A"}',                        'size': 'xs',
                        'color': '#999999',
                    },
                    {
                        'type': 'text',
                        'text': f'今日營業時間: {today_hours}',
                        'size': 'xs',
                        'color': '#aaaaaa',
                        'wrap': True,
                    },
                ],
                'action': {
                    'type': 'postback',
                    'data': f'action=view_detail&place_id={fav.cafe.place_id}',
                }
            }
            contents.append(shop_box)
            if i < len(favorites):
                contents.append({'type': 'separator', 'margin': 'sm'})

        flex_dict = {
            'type': 'bubble',
            'body': {
                'type': 'box',
                'layout': 'vertical',
                'contents': contents,
            }
        }

        alt_text = '我的收藏清單' if page_num == 1 else f'我的收藏清單（第 {page_num} 頁）'
        return FlexMessage(
            alt_text=alt_text,
            contents=FlexBubble.from_dict(flex_dict),
        )


from line_bot.builders.quick_reply import QuickReplyBuilder
