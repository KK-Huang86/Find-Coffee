import logging
import os
import re

from requests.exceptions import RequestException, Timeout

import requests

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
                'address': shop.get('formatted_address'),
                'place_id': shop.get('place_id'),
                'rating': shop.get('rating')
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

        # 移除 "台灣" 字樣
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
