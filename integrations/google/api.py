import logging
import re
from decouple import config

import requests
from django.core.cache import cache
from requests.exceptions import RequestException, Timeout

from utils.cache_guard import get_or_fetch, jittered_ttl, make_key

logger = logging.getLogger(__name__)


class OutOfServiceAreaError(Exception):
    pass
    # 不符合搜尋範圍者


class GoogleAPI:
    GOOGLE_API_KEY = config('GOOGLE_API_KEY')
    # 壓測時以環境變數指向 mock server，避免打到真的 Google
    MAPS_BASE_URL = config('GOOGLE_MAPS_BASE_URL', default='https://maps.googleapis.com')
    BASE_URL = f'{MAPS_BASE_URL}/maps/api/place'
    PHOTO_URL = f'{BASE_URL}/photo'
    GEOCODE_URL = f'{MAPS_BASE_URL}/maps/api/geocode/json'

    # 金鑰被拒或額度用盡時，所有店家的 Detail 都會失敗，暫停一段時間避免每間店都白打一次
    DETAIL_PAUSE_CACHE_KEY = 'google:places_detail:paused'
    DETAIL_PAUSE_SECONDS = 300
    DETAIL_PAUSE_STATUSES = ('REQUEST_DENIED', 'OVER_QUERY_LIMIT')

    # 搜尋結果共用快取：只快取確定的結果（OK / ZERO_RESULTS），暫時性錯誤不快取
    CACHEABLE_STATUSES = ('OK', 'ZERO_RESULTS')
    TEXT_SEARCH_CACHE_TTL = 24 * 60 * 60
    GEOCODE_CACHE_TTL = 7 * 24 * 60 * 60
    NEARBY_CACHE_TTL = 24 * 60 * 60
    # 空結果（ZERO_RESULTS、全部在服務範圍外）以較短 TTL 快取，防止快取穿透
    EMPTY_RESULT_CACHE_TTL = 10 * 60

    # Places Detail 回這些狀態代表 place_id 不存在或格式錯誤，重試不會成功
    DETAIL_MISSING_STATUSES = ('NOT_FOUND', 'INVALID_REQUEST')
    MISSING_PLACE_CACHE_TTL = 60 * 60

    # 台北、新北、基隆的邊界框
    AREA_BOUNDS = {
        'sw': {'lat': 24.84, 'lng': 121.28},
        'ne': {'lat': 25.30, 'lng': 122.05},
    }

    @staticmethod
    def _is_within_service_area(lat, lng):

        if lat is None or lng is None:
            return False

        bounds = GoogleAPI.AREA_BOUNDS
        return (bounds['sw']['lat'] <= lat <= bounds['ne']['lat'] and
                bounds['sw']['lng'] <= lng <= bounds['ne']['lng'])

    @staticmethod
    def search_coffee_shops(shop_name):
        """Text Search 取得 place_id，結果以正規化後的店名共用快取"""
        return get_or_fetch(
            make_key('textsearch', shop_name),
            lambda: GoogleAPI._fetch_text_search(shop_name),
            ttl=GoogleAPI.TEXT_SEARCH_CACHE_TTL,
            empty_ttl=GoogleAPI.EMPTY_RESULT_CACHE_TTL,
        )

    @staticmethod
    def _fetch_text_search(shop_name):
        """
        Returns:
            tuple: (shops, cacheable)；逾時、連線失敗、錯誤狀態時 cacheable=False
        """
        search_url = f'{GoogleAPI.BASE_URL}/textsearch/json'
        params = {
            'query': shop_name,
            'type': 'cafe',
            'key': GoogleAPI.GOOGLE_API_KEY,
            'language': 'zh-TW',
            'region': 'tw',
            'location': '25.05,121.55',
            'radius': 40000,
        }

        try:
            response = requests.get(search_url, params=params, timeout=5)
            response.raise_for_status()
            search_result = response.json()

        except Timeout:
            logger.warning('Google API 請求逾時')
            return [], False

        except RequestException as e:
            logger.error(f'Google API 請求失敗: {e}')
            return [], False

        status = search_result.get('status')
        if status not in GoogleAPI.CACHEABLE_STATUSES:
            logger.warning(f'Text Search 回應非 OK (status: {status})')
            return [], False

        if status != 'OK' or not search_result.get('results'):
            return [], True

        results = search_result['results'][:10]  # 若有多筆資料，僅取前十筆

        shops = []
        for shop in results:
            location = shop.get('geometry', {}).get('location', {})
            lat = location.get('lat')
            lng = location.get('lng')
            if not GoogleAPI._is_within_service_area(lat, lng):
                continue
            shops.append({
                'name': shop.get('name'),
                'place_id': shop.get('place_id'),
            })

        return shops, True

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

        if GoogleAPI.is_known_missing_place(place_id):
            logger.info(f'place_id 先前已確認無效，跳過 Places Detail: {place_id}')
            return {}

        if cache.get(GoogleAPI.DETAIL_PAUSE_CACHE_KEY):
            logger.warning(f'Places Detail 暫停中（金鑰被拒或額度用盡），跳過 place_id: {place_id}')
            return {}

        details_url = f'{GoogleAPI.BASE_URL}/details/json'
        details_params = {
            'place_id': place_id,
            'key': GoogleAPI.GOOGLE_API_KEY,
            'language': 'zh-TW',
            'fields': 'name,formatted_address,formatted_phone_number,opening_hours,rating,user_ratings_total,geometry,url,website,photo,reviews'
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

        status = details_result.get('status')
        if status != 'OK':
            # 不記錄 request URL / params，避免 API key 寫入 log
            logger.warning(
                f'Places Detail 回應非 OK (status: {status}, place_id: {place_id}, '
                f'error_message: {details_result.get("error_message")})'
            )
            if status in GoogleAPI.DETAIL_MISSING_STATUSES:
                cache.set(
                    GoogleAPI._missing_place_key(place_id), True,
                    timeout=jittered_ttl(GoogleAPI.MISSING_PLACE_CACHE_TTL),
                )
            if status in GoogleAPI.DETAIL_PAUSE_STATUSES:
                cache.set(GoogleAPI.DETAIL_PAUSE_CACHE_KEY, status, timeout=GoogleAPI.DETAIL_PAUSE_SECONDS)
                logger.error(f'Places Detail 回應 {status}，暫停所有 Detail 呼叫 {GoogleAPI.DETAIL_PAUSE_SECONDS} 秒')
            return {}

        if not details_result.get('result'):
            return {}

        result = details_result.get('result', {})
        location = result.get('geometry', {}).get('location', {})

        # 處理地址：移除郵遞區號前綴
        address = result.get('formatted_address', '')
        clean_address = GoogleAPI._clean_taiwan_address(address)

        # photo
        photos = result.get('photos', [])
        photo_reference = photos[0].get('photo_reference') if photos else ''

        raw_reviews = result.get('reviews', [])
        reviews = [r.get('text', '') for r in raw_reviews[:5] if r.get('text')]

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
            'website': result.get('website', '無提供'),
            'photo_reference': photo_reference,
            'reviews': reviews,
        }
        return info

    @staticmethod
    def _missing_place_key(place_id):
        # place_id 區分大小寫，不做正規化
        return f'google:v1:detail_missing:{place_id}'

    @staticmethod
    def is_known_missing_place(place_id):
        """place_id 是否在 MISSING_PLACE_CACHE_TTL 內被 Google 確認為無效"""
        if not place_id:
            return False
        return bool(cache.get(GoogleAPI._missing_place_key(place_id)))

    @staticmethod
    def _geocode_address(address):
        """將地址轉換為經緯度，結果以正規化後的地址共用快取"""
        return get_or_fetch(
            make_key('geocode', address),
            lambda: GoogleAPI._fetch_geocode(address),
            ttl=GoogleAPI.GEOCODE_CACHE_TTL,
            empty_ttl=GoogleAPI.EMPTY_RESULT_CACHE_TTL,
        )

    @staticmethod
    def _fetch_geocode(address):
        """
        Returns:
            tuple: ({'lat', 'lng'} 或 {}, cacheable)；逾時、連線失敗、錯誤狀態時 cacheable=False
        """
        search_url = GoogleAPI.GEOCODE_URL
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
            return {}, False

        except RequestException as e:
            logger.error(f'Google API 請求失敗: {e}')
            return {}, False

        status = search_result.get('status')
        if status not in GoogleAPI.CACHEABLE_STATUSES:
            logger.warning(f'Geocoding 回應非 OK (status: {status})')
            return {}, False

        results = search_result.get('results')
        if status != 'OK' or not results:
            logger.warning('Google API 未返回任何結果')
            return {}, True
        result = results[0]

        loction = result['geometry']['location']
        lat = loction['lat']
        lng = loction['lng']

        if lat is None or lng is None:
            logger.warning('Google API 結果缺少經緯度資料')
            return {}, False

        return {'lat': lat, 'lng': lng}, True

    @staticmethod
    def search_nearby_coffee_shops(address=None, lat=None, lng=None):
        """根據地址搜尋附近咖啡店"""

        if lat is None and lng is None:

            coords = GoogleAPI._geocode_address(address)
            if not coords:
                return []

            lat = coords['lat']
            lng = coords['lng']

        if not GoogleAPI._is_within_service_area(lat, lng):
            logger.warning(f'位置 ({lat}, {lng}) 超出服務範圍（台北、新北、基隆）')
            raise OutOfServiceAreaError

        # 四捨五入到小數第 4 位（約 11 公尺），搜尋半徑 100 公尺，誤差可接受
        return get_or_fetch(
            make_key('nearby', f'{lat:.4f},{lng:.4f}'),
            lambda: GoogleAPI._fetch_nearby(lat, lng),
            ttl=GoogleAPI.NEARBY_CACHE_TTL,
            empty_ttl=GoogleAPI.EMPTY_RESULT_CACHE_TTL,
        )

    @staticmethod
    def _fetch_nearby(lat, lng):
        """
        Returns:
            tuple: (shops, cacheable)；逾時、連線失敗、錯誤狀態時 cacheable=False
        """
        search_url = f'{GoogleAPI.BASE_URL}/nearbysearch/json'
        params = {
            'location': f'{lat},{lng}',
            'radius': 100,  # 搜尋半徑 100 公尺
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
            return [], False

        except RequestException as e:
            logger.error(f'Google API 請求失敗: {e}')
            return [], False

        status = search_result.get('status')
        if status not in GoogleAPI.CACHEABLE_STATUSES:
            logger.error(f'Google API 未返回有效結果，status: {status}')
            return [], False

        if status != 'OK' or not search_result.get('results'):
            return [], True

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
            # (VOTE_THRESHOLD(最少需要多少人評分) * AVERAGE_RATING(假設的整體平均評分數) + rating(實際評分) * N(實際評分人數)) / (VOTE_THRESHOLD(最少需要多少人評分) + N(實際評分人數)

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

        target_cafes = sorted_places[:10]

        shops = [
            {'place_id': shop['place_id'], 'name': shop['name'], 'rating': shop['original_rating'],
             'weighted_rating': shop['weighted_rating']}
            for shop in target_cafes
        ]

        return shops, True
