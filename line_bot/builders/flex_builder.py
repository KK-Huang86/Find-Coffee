import json
import logging
import requests
from datetime import date
from urllib.parse import urlencode
from typing import Union
from decouple import config

from linebot.v3.messaging import (
    ReplyMessageRequest,
    TextMessage,
    FlexContainer,
    TemplateMessage,
    FlexMessage,
    FlexCarousel,
    FlexBubble,
    QuickReply,
    QuickReplyItem,
    LocationAction,
    PostbackAction,
)

from users.models import User
from line_bot.utils import parse_opening_hours
from line_bot.constants import MenuText, MenuAction, VOTE_OPTIONS
from line_bot.services.search_cache import SearchHistoryService

logger = logging.getLogger(__name__)


class FlexMessageBuilder:
    WEEKDAYS = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']
    CLOSED_TEXTS = {'休息', '公休', 'Closed'}
    DEFAULT_PHOTO_URL = 'https://developers.line.biz/assets/images/services/bot-designer-icon.png'
    # 標籤樣式配置
    TAG_STYLES = {
        'socket': {
            'color': '#0F5132',
            'backgroundColor': '#D1E7DD',
        },
        'limited_time': {
            'color': '#055160',
            'backgroundColor': '#CFF4FC',
        },
        'has_pet': {
            'color': '#6B3A2A',
            'backgroundColor': '#F5E6D3',
        },
        'pet_friendly': {
            'color': '#5C4B00',
            'backgroundColor': '#FFF3CD',
        },
    }

    @staticmethod
    def get_photo_url(cafe_dict_or_obj):
        """
        取得照片 URL 的優先順序：
        1. S3 URL -> 若已經查詢過會異步存到 S3，再從 S3 抓下來
        2. resolve Google Photo URL -> 透過 photo_reference 去抓取實際的圖片 url（僅限第一次）
        3. 預設圖 -> 若沒有設定 photo_reference，給預設圖

        Args:
            cafe_dict_or_obj: dict 或 Cafe model 物件

        Returns:
            str: 照片 URL
        """

        if not isinstance(cafe_dict_or_obj, dict):
            # 如果是 Cafe 物件，轉換為字典以統一處理
            cafe_dict_or_obj = cafe_dict_or_obj.to_dict()

        photo_s3_url = cafe_dict_or_obj.get('photo_s3_url', '')
        photo_reference = cafe_dict_or_obj.get('photo_reference', '')
        place_id = cafe_dict_or_obj.get('place_id', '')

        if photo_s3_url:
            logger.info(f'place_id: {place_id}, photo_s3_url: {photo_s3_url}，從S3 拉資料')
            return photo_s3_url


        elif photo_reference:
            logger.info(f'place_id: {place_id}, photo_reference: {photo_reference}，解析google photo')
            resolved_url = FlexMessageBuilder.resolve_photo_url(photo_reference)

            if resolved_url != FlexMessageBuilder.DEFAULT_PHOTO_URL:
                FlexMessageBuilder._trigger_s3_upload(place_id)

            return resolved_url

        else:
            logger.info(f'place_id: {place_id}，因沒有設定圖片，使用預設圖')
            return FlexMessageBuilder.DEFAULT_PHOTO_URL

    @staticmethod
    def _trigger_s3_upload(place_id: str):
        """
        觸發背景任務上傳照片到 S3

        這是異步任務，不會阻塞主流程

        Args:
            place_id: Google Places ID
        """
        try:
            from cafe.tasks import download_and_upload_cafe_photo
            from cafe.models import Cafe

            # 取得 cafe 物件
            cafe = Cafe.objects.filter(place_id=place_id).first()
            if cafe and not cafe.photo_s3_url:
                logger.info(f'觸發背景任務：上傳照片到 S3 - {place_id}')
                result = download_and_upload_cafe_photo.delay(cafe.id)
                logger.warning(f'Celery task sent: {result.id}')
            else:
                logger.debug('跳過背景任務（已有 S3 URL 或找不到 cafe）')
        except Exception as e:
            logger.error(f'觸發背景任務失敗: {e}')

    @staticmethod
    def resolve_photo_url(photo_reference: str) -> str:
        """解析 Google Places Photo API 重導向，取得實際圖片 URL"""
        if not photo_reference:
            return FlexMessageBuilder.DEFAULT_PHOTO_URL

        photo_api_url = (
            f'https://maps.googleapis.com/maps/api/place/photo'
            f'?photo_reference={photo_reference}'
            f'&maxwidth=400'
            f'&key={config("GOOGLE_API_KEY")}'
        )

        try:
            response = requests.head(photo_api_url, allow_redirects=True, timeout=2)
            if response.status_code == 200:
                return response.url
        except requests.RequestException as e:
            logger.warning(f'解析 Google photo URL 失敗 (reference: {photo_reference}): {e}')
        return FlexMessageBuilder.DEFAULT_PHOTO_URL

    @staticmethod
    def _create_attribute_tags(info: dict) -> list:
        """
        根據咖啡店屬性生成標籤列表，抓是否有插座 跟 限時資訊

        Args:
            info: 包含 has_socket 和 limited_time 的字典

        Returns:
            list: 標籤元素列表，可能為空
        """
        tags = []

        # 插座標籤：yes/maybe 顯示，no 不顯示
        has_socket = info.get('has_socket')
        if has_socket in ('yes', 'maybe'):
            tags.append(FlexMessageBuilder._create_tag_element(
                text='🔌 有插座',
                tag_type='socket'
            ))

        # 店家是否有貓貓狗狗：yes/maybe 顯示，no 不顯示
        has_pet = info.get('has_pet')
        if has_pet in ('yes', 'maybe'):
            tags.append(FlexMessageBuilder._create_tag_element(
                text='🐈 有貓貓狗狗',
                tag_type='has_pet'
            ))

        # 店家是否為寵物友善：yes/maybe 顯示，no 不顯示
        pet_friendly = info.get('pet_friendly')
        if pet_friendly in ('yes', 'maybe'):
            tags.append(FlexMessageBuilder._create_tag_element(
                text='🐕 寵物友善',
                tag_type='pet_friendly'
            ))

        # 限時標籤：根據值顯示不同文字
        limited_time = info.get('limited_time')
        limited_time_text_map = {
            'no': '⏱ 不限時',
            'maybe': '⏱ 視情況',
            'yes': '⏱ 有限時',
        }
        limited_time_text = limited_time_text_map.get(limited_time)

        if limited_time_text:
            tags.append(FlexMessageBuilder._create_tag_element(
                text=limited_time_text,
                tag_type='limited_time'
            ))

        return tags

    @staticmethod
    def _create_tag_element(text: str, tag_type: str) -> dict:
        """
        創建單個標籤元素

        Args:
            text: 標籤文字
            tag_type: 標籤類型 ('socket','limited_time','has_pet','pet_friendly')

        Returns:
            dict: Flex Message text element
        """
        style = FlexMessageBuilder.TAG_STYLES.get(tag_type, {})
        return {
            'type': 'text',
            'text': text,
            'size': 'xs',
            'color': style.get('color', '#666666'),
            'backgroundColor': style.get('backgroundColor', '#EEEEEE'),
            'paddingStart': '8px',
            'paddingEnd': '8px',
            'paddingTop': '4px',
            'paddingBottom': '4px',
            'cornerRadius': '12px',
            'flex': 0
        }

    @staticmethod
    def _create_tags_box(tags: list) -> dict:
        """
        創建標籤容器 box

        Args:
            tags: 標籤元素列表

        Returns:
            dict: Flex Message box element
        """
        return {
            'type': 'box',
            'layout': 'horizontal',
            'spacing': 'sm',
            'margin': 'md',
            'contents': tags
        }

    # 處理營業時間格式
    @staticmethod
    def format_opening_hours(open_hours: Union[dict, list]):
        """將營業時間列表格式化為簡潔字串"""

        if not open_hours:
            return '營業時間未提供'

        """
        1. 從資料庫拉出來的營業時間範例：-> dict
        'opening_hours':
        {'星期一: 12:00 – 00:00', '星期二: 12:00 – 00:00', '星期四: 12:00 – 00:00', '星期五: 12:00 – 00:00', '星期六: 12:00 – 00:00', '星期日: 12:00 – 00:00'}

        2. 從 Google API 拉出來的營業時間範例： -> list
        ['星期一: 12:00 – 20:00', '星期二: 12:00 – 20:00', '星期三: 12:00 – 20:00', '星期四: 12:00 – 20:00', '星期五: 12:00 – 20:00', '星期六: 12:00 – 20:00', '星期日: 12:00 – 20:00']
        """

        if isinstance(open_hours, dict):
            hours_d = open_hours

        else:
            # 處理從 Google API 拉出來的 list 格式
            hours_d = parse_opening_hours(open_hours)

        # 星期對應表
        weekday_index = date.today().isoweekday() - 1  # 轉成 0～6
        today = FlexMessageBuilder.WEEKDAYS[weekday_index]

        if today in hours_d:
            time_str = hours_d[today]
            # 如果是「休息」或「公休」，明確顯示
            if time_str in FlexMessageBuilder.CLOSED_TEXTS:
                return '今日休息'
            return time_str
        return '今日未營業'

    @staticmethod
    def create_shop_flex_message(info, is_multiple=False):

        def _generate_star_icons(rating):
            """根據評分生成星星圖示"""
            if not rating:
                return []

            stars = []
            full_stars = int(rating)  # 整數部分
            has_half_star = (rating - full_stars) >= 0.3  # 0.3以上顯示半星

            # 添加滿星
            for _ in range(full_stars):
                stars.append({
                    'type': 'icon',
                    'size': 'sm',
                    'url': 'https://developers-resource.landpress.line.me/fx/img/review_gold_star_28.png'
                })

            # 添加半星
            if has_half_star and full_stars < 5:
                stars.append({
                    'type': 'icon',
                    'size': 'sm',
                    'url': 'https://developers-resource.landpress.line.me/fx/img/review_gold_star_28.png'
                })
                full_stars += 1

            # 填充灰星到5顆
            for _ in range(5 - full_stars):
                stars.append({
                    'type': 'icon',
                    'size': 'sm',
                    'url': 'https://developers-resource.landpress.line.me/fx/img/review_gray_star_28.png'
                })

            return stars

        # 建立星星評分區塊
        star_icons = _generate_star_icons(info.get('rating'))
        rating_box_contents = star_icons.copy()

        # 添加評分文字
        rating_text = f'{info.get('rating', 'N/A')}'
        if info.get('user_ratings_total'):
            rating_text += f' ({info.get('user_ratings_total')}則評論)'

        rating_box_contents.append({
            'type': 'text',
            'text': rating_text,
            'size': 'sm',
            'color': '#999999',
            'margin': 'md',
            'flex': 0
        })

        # 處理咖啡店照片
        photo_url = FlexMessageBuilder.get_photo_url(info)

        # 建立 Flex Message
        flex_message = {
            'type': 'bubble',
            'hero': {
                'type': 'image',
                'url': photo_url,
                'size': 'full',
                'aspectRatio': '20:13',
                'aspectMode': 'cover',
                'action': {
                    'type': 'uri',
                    'uri': info.get('google_maps', 'https://line.me/')
                }
            },
            'body': {
                'type': 'box',
                'layout': 'vertical',
                'contents': [
                    {
                        'type': 'text',
                        'text': info.get('name', '店家名稱未提供'),
                        'weight': 'bold',
                        'size': 'xl',
                        'wrap': True
                    },
                    {
                        'type': 'box',
                        'layout': 'baseline',
                        'margin': 'md',
                        'contents': rating_box_contents
                    },
                    {
                        'type': 'box',
                        'layout': 'vertical',
                        'margin': 'lg',
                        'spacing': 'sm',
                        'contents': [
                            {
                                'type': 'box',
                                'layout': 'baseline',
                                'spacing': 'sm',
                                'contents': [
                                    {
                                        'type': 'text',
                                        'text': '📍 地址',
                                        'color': '#aaaaaa',
                                        'size': 'sm',
                                        'flex': 2
                                    },
                                    {
                                        'type': 'text',
                                        'text': info.get('address', '地址未提供'),
                                        'wrap': True,
                                        'color': '#666666',
                                        'size': 'sm',
                                        'flex': 5
                                    }
                                ]
                            },
                            {
                                'type': 'box',
                                'layout': 'baseline',
                                'spacing': 'sm',
                                'contents': [
                                    {
                                        'type': 'text',
                                        'text': '📞 電話',
                                        'color': '#aaaaaa',
                                        'size': 'sm',
                                        'flex': 2
                                    },
                                    {
                                        'type': 'text',
                                        'text': info.get('phone', '電話未提供'),
                                        'wrap': True,
                                        'color': '#666666',
                                        'size': 'sm',
                                        'flex': 5
                                    }
                                ]
                            },
                            {
                                'type': 'box',
                                'layout': 'baseline',
                                'spacing': 'sm',
                                'contents': [
                                    {
                                        'type': 'text',
                                        'text': '⏰ 營業',
                                        'color': '#aaaaaa',
                                        'size': 'sm',
                                        'flex': 2
                                    },
                                    {
                                        'type': 'text',
                                        'text': FlexMessageBuilder.format_opening_hours(info.get('opening_hours', {})),
                                        'wrap': True,
                                        'color': '#666666',
                                        'size': 'sm',
                                        'flex': 5
                                    }
                                ]
                            }
                        ]
                    }
                ]
            },
            'footer': {
                'type': 'box',
                'layout': 'horizontal',
                'spacing': 'sm',
                'contents': []
            }
        }

        # 插入屬性標籤（在評分之後、詳細資訊之前）
        attribute_tags = FlexMessageBuilder._create_attribute_tags(info)
        if attribute_tags:
            tags_box = FlexMessageBuilder._create_tags_box(attribute_tags)
            # 插入到 body contents 的第三個位置（店名、評分之後）
            flex_message['body']['contents'].insert(2, tags_box)

        if is_multiple:
            # 多筆結果時：顯示「看地圖」與「選擇這間」
            flex_message['footer']['contents'].extend([
                {
                    'type': 'button',
                    'style': 'link',
                    'action': {
                        'type': 'uri',
                        'label': '看地圖 ',
                        'uri': info.get('google_maps', 'https://maps.google.com/')
                    }
                },
                {
                    'type': 'button',
                    'style': 'link',
                    'action': {
                        'type': 'postback',
                        'label': '選擇這間',
                        'data': f'action=view_detail&place_id={info.get("place_id")}',
                    }
                }
            ])
        else:
            # 單筆結果時：顯示「看地圖」與「官方網站」
            flex_message['footer']['contents'].append({
                'type': 'button',
                'style': 'primary',
                'action': {
                    'type': 'uri',
                    'label': '看地圖',
                    'uri': info.get('google_maps', 'https://maps.google.com/')
                }
            })
            if info.get('website') and info.get('website') != '無提供':
                flex_message['footer']['contents'].append({
                    'type': 'button',
                    'style': 'link',
                    'action': {
                        'type': 'uri',
                        'label': '官方網站',
                        'uri': info.get('website')
                    }
                })

        return flex_message


class LineMessageBuilder:

    @staticmethod
    def _get_or_create_shop_info(place_id):
        """
        嘗試從資料庫取得店家資訊，若無，則從 Google API 取得資料並寫入資料庫。
        委託給 helpers.get_or_create_cafe_info 統一處理。
        """
        from line_bot.handlers.helpers import get_or_create_cafe_info
        return get_or_create_cafe_info(place_id)

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
            # 單筆結果
            place_id = shops[0]['place_id']

            info_d, cafe = LineMessageBuilder._get_or_create_shop_info(place_id)

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

        if 2 <= len(shops) <= 5:
            # 多筆結果
            flex_messages = []
            for shop in shops:
                place_id = shop['place_id']

                info_d, _ = LineMessageBuilder._get_or_create_shop_info(place_id)

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

                flex_message.quick_reply = quick_reply

                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[flex_message]
                    )
                )

            else:
                line_bot_api.reply_message_with_http_info(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[TextMessage(text='無法取得店家詳細資訊')]
                    )
                )


class PostbackBuilder:

    @staticmethod
    def create_cafe_action_postback(info_d, is_favorited=False):
        """
        統一的postback 格式為 e.g. action=favorite&pid=XXXX
        action=動作&place_id=XXX
        """

        place_id = info_d['place_id']

        # TODO: data use urlencode(payload)

        favorite_action = {
            'type': 'postback',
            'label': '💔 取消收藏' if is_favorited else '⭐ 收藏',
            'data': f'action=unfavorite&place_id={place_id}' if is_favorited else f'action=favorite&place_id={place_id}'
        }

        buttons_template = {
            'type': 'template',
            'altText': '操作選單',
            'template': {
                'type': 'buttons',
                'text': '想對這間咖啡店做什麼？',
                'actions': [
                    favorite_action,
                    {
                        'type': 'postback',
                        'label': '🔗 分享',
                        'data': f'action=share&place_id={place_id}'
                    },
                    {
                        'type': 'postback',
                        'label': '⭐ 評價',
                        'data': f'action=vote&place_id={place_id}'
                    },
                    {
                        'type': 'postback',
                        'label': '🤖 問問AI',
                        'data': f'action=ask_ai&place_id={place_id}'
                    }
                ]
            }
        }

        button_message = TemplateMessage.from_dict(buttons_template)

        return button_message


class FavoritesMessageBuilder:

    def show_favorites_carousel(user_id):
        """顯示使用者的收藏清單為 Carousel Message(收藏間數小於五間)"""

        user = User.objects.filter(line_user_id=user_id).first()
        if not user:
            return TextMessage(text='找不到會員，請重新操作')

        favorites = user.favorites.select_related('cafe').all()
        if not favorites:
            return TextMessage(text='您還沒有收藏任何咖啡店喔～')

        bubbles = []
        for fav in favorites[:5]:  # Carousel 最多 5 個

            # 轉換成 info_d 格式
            info_d = fav.cafe.to_dict()

            flex_data = FlexMessageBuilder.create_shop_flex_message(
                info_d,
                is_multiple=True
            )

            bubbles.append(FlexBubble.from_dict(flex_data))

        carousel = FlexCarousel(contents=bubbles)
        return FlexMessage(alt_text='我的收藏清單', contents=carousel)

    @staticmethod
    def show_favorites_list(user_id):
        """列表式顯示收藏"""
        user = User.objects.get(line_user_id=user_id)
        favorites = user.favorites.select_related('cafe').all()

        if not favorites:
            return TextMessage(text='您還沒有收藏任何咖啡店喔～')

        # 建立列表內容
        contents = [
            {
                'type': 'text',
                'text': '❤️ 我的收藏',
                'weight': 'bold',
                'size': 'xl',
                'margin': 'md',
            },
            {
                'type': 'separator',
                'margin': 'xxl'
            }
        ]

        for i, fav in enumerate(favorites, 1):
            # 每間咖啡店
            shop_box = {
                'type': 'box',
                'layout': 'vertical',
                'margin': 'lg',
                'spacing': 'sm',
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
                                'flex': 0
                            },
                            {
                                'type': 'text',
                                'text': fav.cafe.name,
                                'weight': 'bold',
                                'size': 'md',
                                'wrap': True,
                                'flex': 1
                            }
                        ]
                    },

                    {
                        'type': 'box',
                        'layout': 'baseline',
                        'spacing': 'sm',
                        'contents': [
                            {
                                'type': 'text',
                                'text': fav.cafe.address,
                                'size': 'sm',
                                'color': '#aaaaaa',
                                'flex': 0
                            }
                        ]
                    },

                    {
                        'type': 'box',
                        'layout': 'baseline',
                        'spacing': 'sm',
                        'contents': [
                            {
                                'type': 'text',
                                'text': '⭐',
                                'size': 'sm',
                                'flex': 0
                            },
                            {
                                'type': 'text',
                                'text': str(fav.cafe.rating or 'N/A'),
                                'size': 'sm',
                                'color': '#999999',
                                'flex': 1
                            },
                        ]
                    },

                    {
                        'type': 'box',
                        'layout': 'baseline',
                        'spacing': 'sm',
                        'contents': [
                            {
                                'type': 'text',
                                'text': f'今日營業時間: {FlexMessageBuilder.format_opening_hours(fav.cafe.opening_hours)}',
                                'wrap': True,
                                'size': 'sm',
                                'color': '#aaaaaa'
                            },
                        ]
                    },
                ],
                'action': {
                    'type': 'postback',
                    'data': f'action=view_detail&place_id={fav.cafe.place_id}'
                }
            }
            contents.append(shop_box)

            # 分隔線
            if i < len(favorites):
                contents.append({
                    'type': 'separator',
                    'margin': 'md'
                })

        flex_message = {
            'type': 'bubble',
            'body': {
                'type': 'box',
                'layout': 'vertical',
                'contents': contents
            }
        }

        return FlexMessage(
            alt_text='我的收藏清單',
            contents=FlexBubble.from_dict(flex_message)
        )


class QuickReplyBuilder:

    @staticmethod
    def create_search_again_actions():
        """
        搜尋後的通用快速回覆
        適用情境: 單一咖啡店、多間咖啡店(2-4間)
        """
        return QuickReply(
            items=[
                QuickReplyItem(
                    action=PostbackAction(
                        label='🔍 再找一間',
                        data=f'action=menu&type={MenuAction.SEARCH_SHOP_NAME}'
                    )
                ),
                QuickReplyItem(
                    action=PostbackAction(
                        label='📍 附近搜尋',
                        data=f'action=menu&type={MenuAction.SHARE_LOCATION}'
                    )
                ),
                QuickReplyItem(
                    action=PostbackAction(
                        label='❤️ 我的收藏',
                        data=f'action=menu&type={MenuAction.FAVORITES}'
                    )
                )
            ]
        )

    @staticmethod
    def create_carousel_pagination_actions(has_more=False):
        """
        搜尋後的通用快速回覆
        適用情境: 搜尋地名、分享位置（5間以上）
        """
        return QuickReply(
            items=[
                QuickReplyItem(
                    action=PostbackAction(
                        label='🔍 再用路名查一次',
                        data=f'action=menu&type={MenuAction.SEARCH_ADDRESS}'
                    )
                ),
                QuickReplyItem(
                    action=PostbackAction(
                        label='🔍 店名查詢',
                        data=f'action=menu&type={MenuAction.SEARCH_SHOP_NAME}'
                    )
                ),
                QuickReplyItem(
                    action=PostbackAction(
                        label='📍 附近搜尋',
                        data=f'action=menu&type={MenuAction.SHARE_LOCATION}'
                    )
                ),
                QuickReplyItem(
                    action=PostbackAction(
                        label='❤️ 我的收藏',
                        data=f'action=menu&type={MenuAction.FAVORITES}'
                    )
                )
            ]
        )

    @staticmethod
    def create_location_request():
        """
        請求使用者分享位置的快速回覆
        """
        return QuickReply(
            items=[
                QuickReplyItem(
                    action=LocationAction(
                        label='📍 分享目前位置',
                        text=MenuText.SHARE_LOCATION
                    )
                )
            ]
        )

    @staticmethod
    def create_recent_search_quick_reply(user_id):
        """產生最近搜尋的 Quick Reply"""
        history = SearchHistoryService.get_search_history(user_id)

        if not history:
            return None

        items = []
        for record in history[:5]:
            keyword = record['keyword']
            search_type = record['type']
            place_id = record.get('place_id')

            icon = '☕️' if search_type == "shop_name" else '📍'

            label = f'{icon} {keyword}'
            label = label[:18]  # 保守限制

            payload = {
                'action': 'recent_search',
                'type': search_type,
                'keyword': keyword,
                'place_id': place_id,
            }

            data = urlencode(payload)

            items.append(
                QuickReplyItem(
                    action=PostbackAction(
                        label=label,
                        data=data,
                        display_text=keyword  # 用戶點擊後顯示的文字
                    )
                )
            )

        return QuickReply(items=items)

    @staticmethod
    def create_more_info_actions():
        """更多功能的選項"""
        return QuickReply(
            items=[
                QuickReplyItem(
                    action=PostbackAction(
                        label='🏙️ 工作友善咖啡',
                        data=f'action=menu&type={MenuAction.DISTRICT_SEARCH}'
                    )
                ),
                QuickReplyItem(
                    action=PostbackAction(
                        label='🐈 有貓貓狗狗的咖啡廳',
                        data=f'action=menu&type={MenuAction.PET_SEARCH}'
                    )
                ),
                QuickReplyItem(
                    action=PostbackAction(
                        label='🐕 寵物友善咖啡廳',
                        data=f'action=menu&type={MenuAction.PET_FRIENDLY_SEARCH}'
                    )
                ),
            ]
        )

    @staticmethod
    def create_district_search_actions(search_type, keyword, next_offset, has_more=False):
        """
        工作友善 / 寵物搜尋結果後的快速回覆
        - 固定顯示「重新搜尋」
        - has_more=True 時額外顯示「下一頁」
        """
        # 重新搜尋對應的 postback
        re_search_map = {
            'district': f'action=menu&type={MenuAction.DISTRICT_SEARCH}',
            'pet': f'action=menu&type={MenuAction.PET_SEARCH}',
            'pet_friendly': f'action=menu&type={MenuAction.PET_FRIENDLY_SEARCH}',
            'all_pet': 'action=all_pet_search',
        }
        re_search_data = re_search_map.get(search_type, f'action=menu&type={MenuAction.SEARCH_SHOP_NAME}')

        items = [
            QuickReplyItem(
                action=PostbackAction(
                    label='🔍 重新搜尋',
                    data=re_search_data
                )
            )
        ]

        if has_more:
            from urllib.parse import urlencode
            next_data = urlencode({
                'action': 'next_page',
                'search_type': search_type,
                'keyword': keyword,
                'offset': next_offset,
            })
            items.append(
                QuickReplyItem(
                    action=PostbackAction(
                        label='➡️ 下一頁',
                        data=next_data
                    )
                )
            )

        return QuickReply(items=items)

    @staticmethod
    def create_vote_options(attribute):
        """
        產生投票選項的 Quick Reply
        Args:
            attribute: 屬性名稱 (socket, limited_time, quiet, cheap)
        """

        options = VOTE_OPTIONS.get(attribute, [])
        items = []

        for value, label in options:
            items.append(
                QuickReplyItem(
                    action=PostbackAction(
                        label=label,
                        data=f'action=vote_answer&attr={attribute}&value={value}',
                        display_text=label
                    )
                )
            )

        return QuickReply(items=items)
