import json
import logging
from datetime import date

from linebot.v3.messaging import (
    ReplyMessageRequest,
    TextMessage,
    FlexContainer,
    TemplateMessage,
    FlexMessage,
    FlexCarousel,
    FlexBubble
)

from integrations.google.api import GoogleAPI
from line_bot.models import Cafe, User
from line_bot.utils import parse_opening_hours

logger = logging.getLogger(__name__)


class FlexMessageBuilder:
    WEEKDAYS = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']

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

        # 處理營業時間格式
        def _format_opening_hours(open_hours: dict):
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
                hours_d = {}
                for day_info in open_hours:
                    if ': ' in day_info:
                        day, time_str = day_info.split(': ', 1)
                        hours_d[day] = time_str

            # 星期對應表
            weekday_index = date.today().isoweekday() - 1  # 轉成 0～6
            today = FlexMessageBuilder.WEEKDAYS[weekday_index]

            if today in hours_d:
                time_str = hours_d[today]
                # 如果是「休息」或「公休」，明確顯示
                if time_str in ['休息', '公休', 'Closed']:
                    return f'今日休息'
                return time_str

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

        # 建立 Flex Message
        flex_message = {
            'type': 'bubble',
            'hero': {
                'type': 'image',
                'url': 'https://developers-resource.landpress.line.me/fx/img/01_1_cafe.png',
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
                                        'text': _format_opening_hours(info.get('opening_hours', {})),
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

        Args:
            place_id (str): Google Places ID.

        Returns:
            tuple: (info_d, cafe_obj)
                   info_d (dict): 包含店家詳細資訊的字典。
                   cafe_obj (Cafe): 相關的 Cafe Model 實例。
                   若失敗，則回傳 (None, None)。
        """
        cafe = Cafe.objects.filter(place_id=place_id).first()

        if cafe:
            # 1. 資料庫有 → 直接轉換
            info_d = cafe.to_dict()
            return info_d, cafe

        # 2. 資料庫無 → 呼叫 Google API
        info_d = GoogleAPI.get_shop_detail(place_id)

        """
        {
             'name': '點二咖啡(公休日請看ig 精選限動，不接待超過四人、無插座、禁帶寵物）',
             'address': '台北市中山区民族东路208號2樓', 
             'phone': '無提供', 
             'rating': Decimal('4.4'),
             'user_ratings_total': 657, 
             'place_id': 'ChIJl9JYfaupQjQR8E80com/?cid=17207212494665568240',
             'website': 'https://www.facebook.com/point2coffee/', 
             'lat': 25.0681271, 'lng': 121.5311919,
             'opening_hours': {'星期一': '12:00 – 18:00',
              '星期二': '12:00 – 18:00', 
              '星期三': '12:00 – 18:00',
              '星期四': '12:00 - 18:00', 
              '星期五': '12:00 – 18:00', 
              '星期六': '12:00 – 18:00',
              '星期日': '12:00 – 18:00'}
        }
        """

        if not info_d:
            return None, None

        if not info_d.get('place_id'):
            logger.error('缺少 place_id,無法建立店家資料')
            return None, None

        # 3. 解析並寫入資料庫
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
                google_maps=info_d.get('google_maps') or '未提供地圖連結',
                website=info_d.get('website') or '未提供網站',
                lat=info_d.get('lat') or 0.0,
                lng=info_d.get('lng') or 0.0,
                opening_hours=opening_hours_d
            )
            return cafe.to_dict(), cafe  # 使用新建立的 cafe 物件的 to_dict

        except Exception as e:
            logger.error(f'儲存或解析店家資料時發生錯誤: {e}', exc_info=True)
            return None, None

    @staticmethod
    def send_shop_result(line_bot_api, reply_token, shops, user):

        if not shops:
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

                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[
                            FlexMessage(
                                alt_text=f'找到 {len(flex_messages)} 間咖啡店',
                                contents=FlexContainer.from_dict(carousel)
                            )
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


class PostbackBuilder:

    @staticmethod
    def create_cafe_action_postback(info_d, is_favorited=False):
        """
        統一的postback 格式為 e.g. action=favorite&pid=XXXX
        action=動作&place_id=XXX
        """

        place_id = info_d['place_id']

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
                        'label': '📞 撥打電話',
                        'data': f'action=call&place_id={place_id}'
                    },
                    {
                        'type': 'postback',
                        'label': '🔗 分享',
                        'data': f'action=share&place_id={place_id}'
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
                'margin': 'md'
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
                            }
                        ]
                    }
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
