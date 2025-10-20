import logging
import os
import re
from datetime import date

import requests
from requests.exceptions import RequestException, Timeout

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
                    'style': 'primary',
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
                        'data': f'select_place_id={info.get("place_id")}',
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
