import json
import logging
import os
import re
from datetime import date

import requests
from django.db import transaction, IntegrityError
from linebot.v3.messaging import (
    ReplyMessageRequest,
    TextMessage,
    FlexContainer,
    TemplateMessage,
    FlexMessage,
    FlexCarousel,
    FlexBubble
)
from requests.exceptions import RequestException, Timeout

from line_bot.models import Cafe, Favorite, User

logger = logging.getLogger(__name__)


class GoogleAPI:
    GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
    BASE_URL = 'https://maps.googleapis.com/maps/api/place'

    @staticmethod
    def search_coffee_shops(shop_name):
        #  Text Search 取得 place_id
        search_url = f'{GoogleAPI.BASE_URL}/textsearch/json'
        params = {
            'query': f'{shop_name} 咖啡店',
            'type': 'cafe',
            'key': GoogleAPI.GOOGLE_API_KEY,
            'language': 'zh-TW'
        }

        try:
            response = requests.get(search_url, params=params, timeout=5)
            response.raise_for_status()
            search_result = response.json()

        except Timeout:
            logger.warning('Google API 請求逾時')
            return {}

        except RequestException as e:
            logger.error(f'Google API 請求失敗: {e}')
            return {}

        if search_result.get('status') != 'OK' or not search_result.get('results'):
            return {}

        results = search_result['results'][:5]  # 若有多筆資料，僅取前五筆

        shops = []
        for shop in results:
            shops.append({
                'name': shop.get('name'),
                'place_id': shop.get('place_id'),
            })

        return shops

    @staticmethod
    def _clean_taiwan_address(address):
        """
        移除台灣地址的郵遞區號前綴
        例如：'10085台灣台北市中正區晉江街10號' -> '台北市中正區晉江街10號'
        """
        # 移除郵遞區號 (3-6位數字)
        address = re.sub(r'^\d{3,6}', '', address)

        # 移除 '台灣' 字樣
        address = address.replace('台灣', '')

        # 移除開頭的空白
        address = address.strip()

        return address

    @staticmethod
    def get_shop_detail(place_id):
        # Place Details 取得完整資訊

        details_url = f'{GoogleAPI.BASE_URL}/details/json'
        details_params = {
            'place_id': place_id,
            'key': GoogleAPI.GOOGLE_API_KEY,
            'language': 'zh-TW',
            'fields': 'name,formatted_address,formatted_phone_number,opening_hours,rating,user_ratings_total,geometry,url,website'
        }

        try:
            response = requests.get(details_url, params=details_params, timeout=5)
            response.raise_for_status()
            details_result = response.json()

        except Timeout:
            logger.warning('Google API 請求逾時')
            return {}

        except RequestException as e:
            logger.error(f'Google API 請求失敗: {e}')
            return {}

        if details_result.get('status') != 'OK' or not details_result.get('result'):
            return {}

        result = details_result.get('result', {})
        location = result.get('geometry', {}).get('location', {})

        # 處理地址：移除郵遞區號前綴
        address = result.get('formatted_address', '')
        clean_address = GoogleAPI._clean_taiwan_address(address)

        info = {
            'place_id': place_id,
            'name': result.get('name'),
            'address': clean_address,
            'phone': result.get('formatted_phone_number', '無提供'),
            'lat': location.get('lat'),
            'lng': location.get('lng'),
            'rating': result.get('rating'),
            'user_ratings_total': result.get('user_ratings_total'),
            'opening_hours': result.get('opening_hours', {}).get('weekday_text', []),
            'google_maps': result.get('url'),
            'website': result.get('website', '無提供')
        }
        return info

    @staticmethod
    def _geocode_address(address):
        """將地址轉換為經緯度"""

        search_url = 'https://maps.googleapis.com/maps/api/geocode/json'
        params = {
            'address': address,
            'key': GoogleAPI.GOOGLE_API_KEY,
            'language': 'zh-TW',
            'region': 'tw'
        }

        try:
            response = requests.get(search_url, params=params, timeout=5)
            response.raise_for_status()
            search_result = response.json()

        except Timeout:
            logger.warning('Google API 請求逾時')
            return {}

        except RequestException as e:
            logger.error(f'Google API 請求失敗: {e}')
            return {}

        if search_result.get('status') != 'OK' or not search_result.get('results'):
            return {}

        results = search_result.get('results')
        result = results[0]
        if not results:
            logger.warning('Google API 未返回任何結果')
            return {}

        loction = result['geometry']['location']
        lat = loction['lat']
        lng = loction['lng']

        if lat is None or lng is None:
            logger.warning('Google API 結果缺少經緯度資料')
            return {}

        return {'lat': lat, 'lng': lng}

    @staticmethod
    def search_nearby_coffee_shops(address=None, lat=None, lng=None):
        """根據地址搜尋附近咖啡店"""

        if lat is None and lng is None:

            coords = GoogleAPI._geocode_address(address)
            if not coords:
                return []

            lat = coords['lat']
            lng = coords['lng']

        search_url = f'{GoogleAPI.BASE_URL}/nearbysearch/json'
        params = {
            'location': f'{lat},{lng}',
            'radius': 500,  # 搜尋半徑 500 公尺
            'type': 'cafe',
            'keyword': '咖啡店',
            'key': GoogleAPI.GOOGLE_API_KEY,
            'language': 'zh-TW',
            'region': 'tw'
        }

        try:
            response = requests.get(search_url, params=params, timeout=5)
            response.raise_for_status()
            search_result = response.json()

        except Timeout:
            logger.warning('Google API 請求逾時')
            return []

        except RequestException as e:
            logger.error(f'Google API 請求失敗: {e}')
            return []

        if search_result.get('status') != 'OK' or not search_result.get('results'):
            logger.error(f"Google API 未返回有效結果，status: {search_result.get('status')}")
            return []

        results = search_result['results']
        rating_rank = []
        for result in results:
            cafe_place_id = result.get('place_id', '')
            cafe_rating = result.get('rating', 'N/A')
            cafe_rating_dict = {cafe_place_id: cafe_rating}
            rating_rank.append(cafe_rating_dict)

        pairs = [(list(d.keys())[0], list(d.values())[0]) for d in rating_rank]
        sorted_pairs = sorted(pairs, key=lambda x: x[1], reverse=True)
        target_cafes = sorted_pairs[:5]
        # target_cafes 原本是 tuple 格式 ('XXXXXXXXXXX', 4.9)
        shops = [{'place_id': pid, 'rating': rating} for pid, rating in target_cafes]
        return shops


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


class FavoritesManager:

    @staticmethod
    def add_favorite(user, info):

        if not info.get('place_id') or not info.get('name'):
            return False, '咖啡店資訊不完整'

        try:
            with transaction.atomic():
                # 取得或建立咖啡店
                cafe, cafe_created = Cafe.objects.get_or_create(
                    place_id=info['place_id'],
                    defaults={
                        'name': info.get('name', '未命名咖啡店'),
                        'address': info.get('address', ''),
                        'phone': info.get('phone', ''),
                        'lat': info.get('lat'),
                        'lng': info.get('lng'),
                        'rating': info.get('rating'),
                        'user_ratings_total': info.get('user_ratings_total', 0),
                        'google_maps': info.get('google_maps', ''),
                        'website': info.get('website', '')
                    }
                )

                if cafe_created:
                    logger.info(f'建立新咖啡店: {cafe.name} ({cafe.place_id})')

                # 建立收藏關聯
                favorite, created = Favorite.objects.get_or_create(
                    user=user,
                    cafe=cafe
                )

                if created:
                    # 增加收藏數
                    cafe.increment_favorite_count()
                    logger.info(f'使用者 {user.member_code} 收藏 {cafe.name}')
                    return True, f'✅ 已收藏「{cafe.name}」'
                else:
                    return False, f'⚠️ 「{cafe.name}」已在您的收藏清單中'

        except IntegrityError as e:
            logger.error(f'收藏失敗 (IntegrityError): {e}')
            return False, '收藏失敗，請稍後再試'

        except Exception as e:
            logger.error(f'收藏失敗: {e}')
            return False, '系統錯誤，請稍後再試'

    @staticmethod
    def remove_favorite(user, info):

        if not info.get('place_id') or not info.get('name'):
            return False, '咖啡店資訊不完整'

        try:
            with transaction.atomic():
                # 取得咖啡店
                cafe = Cafe.objects.filter(place_id=info['place_id']).first()
                if not cafe:
                    return False, '找不到該咖啡店'

                # 刪除收藏關聯
                favorite = Favorite.objects.filter(user=user, cafe=cafe).first()
                if favorite:
                    favorite.delete()
                    # 減少收藏數
                    cafe.decrement_favorite_count()
                    logger.info(f'使用者 {user.member_code} 取消收藏 {cafe.name}')
                    return True, f'已取消收藏「{cafe.name}」'
                else:
                    return False, f'「{cafe.name}」不在您的收藏清單中'

        except IntegrityError as e:
            logger.error(f'取消收藏失敗 (IntegrityError): {e}')
            return False, '取消收藏失敗，請稍後再試'

        except Exception as e:
            logger.error(f'取消收藏失敗: {e}')
            return False, '系統錯誤，請稍後再試'

    @staticmethod
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
