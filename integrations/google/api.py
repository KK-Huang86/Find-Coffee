import logging
import os
import re

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
            'radius': 100,  # 搜尋半徑 500 公尺
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

        # 貝葉斯平均所需參數
        VOTE_THRESHOLD = 50  # C: 最小必須評分人數
        AVERAGE_RATING = 4.0  # m: 假設的整體平均評分

        results = search_result['results']
        weighted_rank = []

        for result in results:
            rating = result.get('rating', AVERAGE_RATING)  # 無評分時設為平均
            n = result.get('user_ratings_total', 0)  # 實際評分人數

            # 計算加權評分 (weighted_rating)
            # weighted_rating =
            # (VOTE_THRESHOLD(最少需要多少人評分) * AVERAGE_RATING(假設的整體平均評分數) + rating(實際評分) * N(實際評分人數)) / (VOTE_THRESHOLD(最少需要多少人評分) + AVERAGE_RATING(假設的整體平均評分數))

            if n > 0:
                weighted_rating = (VOTE_THRESHOLD * AVERAGE_RATING + rating * n) / (VOTE_THRESHOLD + n)
            else:
                # 如果沒有評分數據，直接使用平均評分
                weighted_rating = AVERAGE_RATING

            """
            [{'place_id': 'ChIJrxF31rCrQjQRCIU4tfV7qbQ',
            'name': '輝葉放空站',
            'original_rating': 4.9,
            'rating_total': 447,
            'weighted_rating': 4.861456102783726},
            """
            weighted_rank.append({
                'place_id': result.get('place_id'),
                'name': result.get('name'),  # 加上 name 方便除錯
                'original_rating': rating,
                'rating_total': n,
                'weighted_rating': weighted_rating  # 使用這個欄位進行排序
            })

        # 根據加權評分進行排序
        sorted_places = sorted(weighted_rank, key=lambda x: x['weighted_rating'], reverse=True)

        target_cafes = sorted_places[:5]

        shops = [
            {'place_id': shop['place_id'], 'rating': shop['original_rating'],
             'weighted_rating': shop['weighted_rating']}
            for shop in target_cafes
        ]

        return shops