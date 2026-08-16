import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.db import close_old_connections

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
    def _resolve_single_photo_url(info):
        """
        單筆店家的照片解析 worker，供 ThreadPoolExecutor 平行呼叫。

        在 worker 執行緒結束前明確關閉 Django DB 連線，避免 PgBouncer
        transaction pooling 下遺留未關閉的連線（見 design.md Decision 3）。
        """
        try:
            return FlexMessageBuilder.get_photo_url(info, allow_sync_resolve=True)
        finally:
            close_old_connections()

    @staticmethod
    def _resolve_photo_urls_concurrently(infos):
        """
        對多筆店家平行呼叫 get_photo_url，回傳 {place_id: photo_url} 對照表。

        任一店家解析拋出例外時，該店家回退為預設圖，不影響其他店家的結果。
        """
        if not infos:
            return {}

        photo_url_map = {}
        with ThreadPoolExecutor(max_workers=len(infos)) as executor:
            future_to_place_id = {
                executor.submit(LineMessageBuilder._resolve_single_photo_url, info): info['place_id']
                for info in infos
            }
            for future in as_completed(future_to_place_id):
                place_id = future_to_place_id[future]
                try:
                    photo_url_map[place_id] = future.result()
                except Exception as e:
                    logger.error(f'平行解析照片 URL 失敗，place_id: {place_id}, error: {e}')
                    photo_url_map[place_id] = FlexMessageBuilder.DEFAULT_PHOTO_URL

        return photo_url_map

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

            # ① 收集所有店家的完整資訊（含 DB 快取命中與 Google API 補查）
            info_ds = []
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
                    info_ds.append(info_d)
                else:
                    logger.warning(f'無法取得店家詳細資訊，place_id: {place_id}')
                    continue

            # ② 平行解析所有店家的照片 URL
            photo_url_map = LineMessageBuilder._resolve_photo_urls_concurrently(info_ds)

            # ③ 組裝 Flex Message，帶入已解析好的照片 URL
            flex_messages = [
                FlexMessageBuilder.create_shop_flex_message(
                    info_d, is_multiple=True, photo_url_override=photo_url_map.get(info_d['place_id'])
                )
                for info_d in info_ds
            ]

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
