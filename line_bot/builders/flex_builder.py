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
from line_bot.models import Cafe
from line_bot.models import User

logger = logging.getLogger(__name__)


class FlexMessageBuilder:

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
        def _format_opening_hours(hours_list):
            """將營業時間列表格式化為簡潔字串"""
            if not hours_list:
                return '營業時間未提供'

            # 取今天和明天的營業時間（簡化顯示）
            """
            'opening_hours': 
            ['星期一: 12:00 – 00:00', '星期二: 12:00 – 00:00', '星期四: 12:00 – 00:00', '星期五: 12:00 – 00:00', '星期六: 12:00 – 00:00', '星期日: 12:00 – 00:00']
            """

            weekday_index = date.today().isoweekday() - 1  # 轉成 0～6
            if weekday_index >= len(hours_list):
                # 避免索引超出範圍
                open_time = hours_list[0]  # 會有個問題，如果超出範圍回傳星期一的話，可能會導致營業時間不準
            else:
                open_time = hours_list[weekday_index]

            # 移除'星期X: '前綴
            open_time = open_time.split(': ', 1)[1] if ': ' in open_time else open_time
            return open_time

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
                                        'text': _format_opening_hours(info.get('opening_hours', [])),
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

            cafe = Cafe.objects.filter(place_id=place_id).first()
            if not cafe:
                info_d = GoogleAPI.get_shop_detail(place_id)

                if not info_d:
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=reply_token,
                            messages=[TextMessage(text='無法取得店家詳細資訊')]
                        )
                    )
                    return

                cafe = Cafe.objects.create(
                    place_id=info_d['place_id'],
                    name=info_d['name'],
                    address=info_d['address'],
                    phone=info_d.get('phone', ''),
                    rating=info_d.get('rating'),
                    user_ratings_total=info_d.get('user_ratings_total', 0),
                    google_maps=info_d.get('google_maps', ''),
                    website=info_d.get('website', ''),
                    lat=info_d.get('lat'),
                    lng=info_d.get('lng')
                )
            else:
                # 資料庫有 → 直接轉換
                info_d = cafe.to_dict()

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

        if 2 <= len(shops) <= 5:
            # 多筆結果
            flex_messages = []
            for shop in shops:
                place_id = shop['place_id']
                info_d = GoogleAPI.get_shop_detail(place_id)
                logger.info(info_d)

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
