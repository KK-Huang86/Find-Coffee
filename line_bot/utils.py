import os
import re

import requests

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
BASE_URL = 'https://maps.googleapis.com/maps/api/place'


def search_coffee_shops(shop_name):
    #  Text Search 取得 place_id
    search_url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {
        'query': f'{shop_name} 咖啡店',
        'type': 'cafe',
        'key': GOOGLE_API_KEY,
        'language': 'zh-TW'
    }
    search_result = requests.get(search_url, params=params).json()

    if search_result['status'] != 'OK' or not search_result['results']:
        return []

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


def get_shop_detail(place_id):
    # Place Details 取得完整資訊

    details_url = "https://maps.googleapis.com/maps/api/place/details/json"
    details_params = {
        'place_id': place_id,
        'key': GOOGLE_API_KEY,
        'language': 'zh-TW',
        'fields': 'name,formatted_address,formatted_phone_number,opening_hours,rating,user_ratings_total,geometry,url,website'
    }
    details_result = requests.get(details_url, params=details_params).json()

    result = details_result.get('result', {})
    location = result.get('geometry', {}).get('location', {})

    # 處理地址：移除郵遞區號前綴
    address = result.get('formatted_address', '')
    clean_address = clean_taiwan_address(address)

    # 整理資料
    info = {
        'name': result.get('name'),
        'address': clean_address,
        'phone': result.get('formatted_phone_number', '無提供'),
        'lat': location.get('lat'),
        'lng': location.get('lng'),
        'rating': result.get('rating'),
        'user_ratings_total': result.get('user_ratings_total'),
        'opening_hours': result.get('opening_hours', {}).get('weekday_text', []),
        'Google Maps': result.get('url'),
        'website': result.get('website', '無提供')
    }

    return info


def clean_taiwan_address(address):
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
