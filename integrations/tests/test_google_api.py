import logging

import pytest
from unittest.mock import MagicMock
from requests.exceptions import RequestException, Timeout

from integrations.google.api import GoogleAPI, OutOfServiceAreaError


class TestGoogleEndpoints:
    """Google API 端點由 GOOGLE_MAPS_BASE_URL 組成，預設為正式網址（壓測時指向 mock server）"""

    def test_default_base_url_is_google(self):
        """未設定環境變數時使用 Google 正式網址"""
        assert GoogleAPI.MAPS_BASE_URL == 'https://maps.googleapis.com'

    def test_endpoints_derive_from_base_url(self):
        """Places、Photo、Geocode 端點皆由 MAPS_BASE_URL 組成"""
        assert GoogleAPI.BASE_URL == 'https://maps.googleapis.com/maps/api/place'
        assert GoogleAPI.PHOTO_URL == 'https://maps.googleapis.com/maps/api/place/photo'
        assert GoogleAPI.GEOCODE_URL == 'https://maps.googleapis.com/maps/api/geocode/json'

    def test_geocode_uses_geocode_url(self, mocker):
        """_geocode_address 呼叫 GEOCODE_URL"""
        mocker.patch.object(GoogleAPI, 'GEOCODE_URL', 'http://mock-google/maps/api/geocode/json')
        mock_get = mocker.patch('integrations.google.api.requests.get', side_effect=Timeout)

        GoogleAPI._geocode_address('台北市')

        assert mock_get.call_args.args[0] == 'http://mock-google/maps/api/geocode/json'


class TestCleanTaiwanAddress:
    """測試 GoogleAPI._clean_taiwan_address"""

    def test_remove_zip_code_and_taiwan(self):
        """移除郵遞區號和台灣字樣"""
        result = GoogleAPI._clean_taiwan_address('10085台灣台北市中正區晉江街10號')
        assert result == '台北市中正區晉江街10號'

    def test_remove_zip_code_only(self):
        """只有郵遞區號，沒有台灣字樣"""
        result = GoogleAPI._clean_taiwan_address('106台北市大安區信義路')
        assert result == '台北市大安區信義路'

    def test_remove_taiwan_only(self):
        """只有台灣字樣，沒有郵遞區號"""
        result = GoogleAPI._clean_taiwan_address('台灣台北市信義區')
        assert result == '台北市信義區'

    def test_no_prefix(self):
        """沒有前綴的地址"""
        result = GoogleAPI._clean_taiwan_address('台北市信義區信義路五段7號')
        assert result == '台北市信義區信義路五段7號'

    def test_empty_string(self):
        """空字串"""
        result = GoogleAPI._clean_taiwan_address('')
        assert result == ''


class TestSearchCoffeeShops:
    """測試 GoogleAPI.search_coffee_shops"""

    def test_success(self, mocker):
        """成功搜尋咖啡店"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'status': 'OK',
            'results': [
                {'name': '星巴克', 'place_id': 'ChIJ001', 'geometry': {'location': {'lat': 25.033, 'lng': 121.564}}},
                {'name': '路易莎', 'place_id': 'ChIJ002', 'geometry': {'location': {'lat': 25.040, 'lng': 121.570}}},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mocker.patch('integrations.google.api.requests.get', return_value=mock_response)

        result = GoogleAPI.search_coffee_shops('星巴克')

        assert len(result) == 2
        assert result[0] == {'name': '星巴克', 'place_id': 'ChIJ001'}
        assert result[1] == {'name': '路易莎', 'place_id': 'ChIJ002'}

    def test_request_params_include_type_cafe(self, mocker):
        """搜尋時帶有 type=cafe 參數，確保只回傳咖啡店類型"""
        mock_response = MagicMock()
        mock_response.json.return_value = {'status': 'OK', 'results': [{'name': '星巴克', 'place_id': 'ChIJ001'}]}
        mock_response.raise_for_status = MagicMock()
        mock_get = mocker.patch('integrations.google.api.requests.get', return_value=mock_response)

        GoogleAPI.search_coffee_shops('星巴克')

        _, kwargs = mock_get.call_args
        params = kwargs.get('params', {})
        assert params.get('type') == 'cafe'

    def test_max_ten_results(self, mocker):
        """最多回傳 10 筆結果"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'status': 'OK',
            'results': [
                {'name': f'咖啡店{i}', 'place_id': f'ChIJ{i:03d}', 'geometry': {'location': {'lat': 25.033, 'lng': 121.564}}}
                for i in range(12)
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mocker.patch('integrations.google.api.requests.get', return_value=mock_response)

        result = GoogleAPI.search_coffee_shops('咖啡')

        assert len(result) == 10

    def test_timeout(self, mocker):
        """請求逾時回傳空列表"""
        mocker.patch('integrations.google.api.requests.get', side_effect=Timeout)

        result = GoogleAPI.search_coffee_shops('星巴克')

        assert result == []

    def test_request_exception(self, mocker):
        """請求失敗回傳空列表"""
        mocker.patch('integrations.google.api.requests.get', side_effect=RequestException('error'))

        result = GoogleAPI.search_coffee_shops('星巴克')

        assert result == []

    def test_status_not_ok(self, mocker):
        """API 狀態非 OK 回傳空列表"""
        mock_response = MagicMock()
        mock_response.json.return_value = {'status': 'ZERO_RESULTS', 'results': []}
        mock_response.raise_for_status = MagicMock()
        mocker.patch('integrations.google.api.requests.get', return_value=mock_response)

        result = GoogleAPI.search_coffee_shops('不存在的店')

        assert result == []

    def test_empty_results(self, mocker):
        """results 為空回傳空列表"""
        mock_response = MagicMock()
        mock_response.json.return_value = {'status': 'OK', 'results': []}
        mock_response.raise_for_status = MagicMock()
        mocker.patch('integrations.google.api.requests.get', return_value=mock_response)

        result = GoogleAPI.search_coffee_shops('不存在的店')

        assert result == []


class TestGetShopDetail:
    """測試 GoogleAPI.get_shop_detail"""

    def _mock_detail_response(self):
        """建立完整的 Place Details 回應"""
        return {
            'status': 'OK',
            'result': {
                'name': '測試咖啡店',
                'formatted_address': '10085台灣台北市中正區晉江街10號',
                'formatted_phone_number': '02-1234-5678',
                'opening_hours': {
                    'weekday_text': ['星期一: 09:00 – 18:00']
                },
                'rating': 4.5,
                'user_ratings_total': 200,
                'geometry': {
                    'location': {'lat': 25.033, 'lng': 121.564}
                },
                'url': 'https://maps.google.com/xxx',
                'website': 'https://example.com',
                'photos': [
                    {'photo_reference': 'ref_abc123'}
                ]
            }
        }

    def test_success(self, mocker):
        """成功取得咖啡店詳細資訊"""
        mock_response = MagicMock()
        mock_response.json.return_value = self._mock_detail_response()
        mock_response.raise_for_status = MagicMock()
        mocker.patch('integrations.google.api.requests.get', return_value=mock_response)

        result = GoogleAPI.get_shop_detail('ChIJ123')

        assert result['place_id'] == 'ChIJ123'
        assert result['name'] == '測試咖啡店'
        assert result['address'] == '台北市中正區晉江街10號'
        assert result['phone'] == '02-1234-5678'
        assert result['lat'] == 25.033
        assert result['lng'] == 121.564
        assert result['rating'] == 4.5
        assert result['user_ratings_total'] == 200
        assert result['opening_hours'] == ['星期一: 09:00 – 18:00']
        assert result['google_maps'] == 'https://maps.google.com/xxx'
        assert result['website'] == 'https://example.com'
        assert result['photo_reference'] == 'ref_abc123'

    def test_no_photos(self, mocker):
        """沒有照片時 photo_reference 為空字串"""
        data = self._mock_detail_response()
        data['result']['photos'] = []

        mock_response = MagicMock()
        mock_response.json.return_value = data
        mock_response.raise_for_status = MagicMock()
        mocker.patch('integrations.google.api.requests.get', return_value=mock_response)

        result = GoogleAPI.get_shop_detail('ChIJ123')

        assert result['photo_reference'] == ''

    def test_missing_optional_fields(self, mocker):
        """缺少選填欄位時使用預設值"""
        data = {
            'status': 'OK',
            'result': {
                'name': '測試咖啡店',
                'geometry': {'location': {'lat': 25.0, 'lng': 121.0}},
            }
        }
        mock_response = MagicMock()
        mock_response.json.return_value = data
        mock_response.raise_for_status = MagicMock()
        mocker.patch('integrations.google.api.requests.get', return_value=mock_response)

        result = GoogleAPI.get_shop_detail('ChIJ123')

        assert result['phone'] == '無提供'
        assert result['website'] == '無提供'
        assert result['opening_hours'] == []
        assert result['photo_reference'] == ''

    def test_timeout(self, mocker):
        """請求逾時回傳空字典"""
        mocker.patch('integrations.google.api.requests.get', side_effect=Timeout)

        result = GoogleAPI.get_shop_detail('ChIJ123')

        assert result == {}

    def test_request_exception(self, mocker):
        """請求失敗回傳空字典"""
        mocker.patch('integrations.google.api.requests.get', side_effect=RequestException('error'))

        result = GoogleAPI.get_shop_detail('ChIJ123')

        assert result == {}

    def test_status_not_ok(self, mocker):
        """API 狀態非 OK 回傳空字典"""
        mock_response = MagicMock()
        mock_response.json.return_value = {'status': 'NOT_FOUND'}
        mock_response.raise_for_status = MagicMock()
        mocker.patch('integrations.google.api.requests.get', return_value=mock_response)

        result = GoogleAPI.get_shop_detail('ChIJ123')

        assert result == {}

    def _mock_status_response(self, mocker, status, error_message=None):
        body = {'status': status}
        if error_message:
            body['error_message'] = error_message
        mock_response = MagicMock()
        mock_response.json.return_value = body
        mock_response.raise_for_status = MagicMock()
        return mocker.patch('integrations.google.api.requests.get', return_value=mock_response)

    @pytest.mark.parametrize('status', ['NOT_FOUND', 'INVALID_REQUEST', 'REQUEST_DENIED', 'OVER_QUERY_LIMIT'])
    def test_status_not_ok_logs_status_and_error_message(self, mocker, caplog, status):
        """狀態非 OK 時記錄 status、error_message 與 place_id"""
        self._mock_status_response(mocker, status, error_message='some reason')

        with caplog.at_level(logging.WARNING, logger='integrations.google.api'):
            GoogleAPI.get_shop_detail('ChIJ123')

        messages = ' '.join(r.getMessage() for r in caplog.records)
        assert status in messages
        assert 'some reason' in messages
        assert 'ChIJ123' in messages

    def test_status_not_ok_log_does_not_leak_api_key(self, mocker, caplog):
        """非 OK 的 log 不含 API key"""
        mocker.patch.object(GoogleAPI, 'GOOGLE_API_KEY', 'secret_key_123')
        self._mock_status_response(mocker, 'REQUEST_DENIED', error_message='The provided API key is invalid.')

        with caplog.at_level(logging.WARNING, logger='integrations.google.api'):
            GoogleAPI.get_shop_detail('ChIJ123')

        assert all('secret_key_123' not in r.getMessage() for r in caplog.records)

    @pytest.mark.parametrize('status', ['REQUEST_DENIED', 'OVER_QUERY_LIMIT'])
    def test_denied_or_over_limit_pauses_subsequent_calls(self, mocker, status):
        """金鑰被拒或額度用盡後，後續呼叫不發出請求，直接回傳空字典"""
        mock_get = self._mock_status_response(mocker, status)

        GoogleAPI.get_shop_detail('ChIJ123')
        result = GoogleAPI.get_shop_detail('ChIJ456')

        assert result == {}
        assert mock_get.call_count == 1

    def test_pause_lasts_300_seconds(self, mocker):
        """暫停旗標 TTL 為 300 秒"""
        self._mock_status_response(mocker, 'REQUEST_DENIED')
        mock_cache_set = mocker.patch('integrations.google.api.cache.set')

        GoogleAPI.get_shop_detail('ChIJ123')

        mock_cache_set.assert_called_once()
        assert mock_cache_set.call_args.kwargs['timeout'] == 300

    def test_paused_call_logs_skip(self, mocker, caplog):
        """暫停期間的呼叫會記錄被跳過"""
        self._mock_status_response(mocker, 'OVER_QUERY_LIMIT')
        GoogleAPI.get_shop_detail('ChIJ123')

        with caplog.at_level(logging.WARNING, logger='integrations.google.api'):
            GoogleAPI.get_shop_detail('ChIJ456')

        assert any('ChIJ456' in r.getMessage() for r in caplog.records)

    @pytest.mark.parametrize('status', ['NOT_FOUND', 'INVALID_REQUEST', 'ZERO_RESULTS'])
    def test_other_not_ok_status_does_not_pause(self, mocker, status):
        """店家不存在等狀態不暫停，後續呼叫仍會發出請求"""
        mock_get = self._mock_status_response(mocker, status)

        GoogleAPI.get_shop_detail('ChIJ123')
        GoogleAPI.get_shop_detail('ChIJ456')

        assert mock_get.call_count == 2


class TestGeocodeAddress:
    """測試 GoogleAPI._geocode_address"""

    def test_success(self, mocker):
        """成功將地址轉換為經緯度"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'status': 'OK',
            'results': [{
                'geometry': {
                    'location': {'lat': 25.033, 'lng': 121.564}
                }
            }]
        }
        mock_response.raise_for_status = MagicMock()
        mocker.patch('integrations.google.api.requests.get', return_value=mock_response)

        result = GoogleAPI._geocode_address('台北市信義區')

        assert result == {'lat': 25.033, 'lng': 121.564}

    def test_timeout(self, mocker):
        """請求逾時回傳空字典"""
        mocker.patch('integrations.google.api.requests.get', side_effect=Timeout)

        result = GoogleAPI._geocode_address('台北市信義區')

        assert result == {}

    def test_request_exception(self, mocker):
        """請求失敗回傳空字典"""
        mocker.patch('integrations.google.api.requests.get', side_effect=RequestException('error'))

        result = GoogleAPI._geocode_address('台北市信義區')

        assert result == {}

    def test_status_not_ok(self, mocker):
        """API 狀態非 OK 回傳空字典"""
        mock_response = MagicMock()
        mock_response.json.return_value = {'status': 'ZERO_RESULTS', 'results': []}
        mock_response.raise_for_status = MagicMock()
        mocker.patch('integrations.google.api.requests.get', return_value=mock_response)

        result = GoogleAPI._geocode_address('不存在的地址')

        assert result == {}


class TestSearchNearbyCoffeeShops:
    """測試 GoogleAPI.search_nearby_coffee_shops"""

    def _mock_nearby_response(self):
        """建立 Nearby Search 回應"""
        return {
            'status': 'OK',
            'results': [
                {'place_id': 'ChIJ001', 'name': '高評分店', 'rating': 4.8, 'user_ratings_total': 500},
                {'place_id': 'ChIJ002', 'name': '中評分店', 'rating': 4.2, 'user_ratings_total': 100},
                {'place_id': 'ChIJ003', 'name': '低評分店', 'rating': 3.5, 'user_ratings_total': 30},
            ]
        }

    def test_success_with_lat_lng(self, mocker):
        """使用經緯度搜尋成功"""
        mock_response = MagicMock()
        mock_response.json.return_value = self._mock_nearby_response()
        mock_response.raise_for_status = MagicMock()
        mocker.patch('integrations.google.api.requests.get', return_value=mock_response)

        result = GoogleAPI.search_nearby_coffee_shops(lat=25.033, lng=121.564)

        assert len(result) == 3
        # 驗證依加權評分排序（高評分店評分人數多，加權後仍最高）
        assert result[0]['place_id'] == 'ChIJ001'

    def test_success_with_address(self, mocker):
        """使用地址搜尋成功（先 geocode 再 nearby search）"""
        mock_geocode = mocker.patch.object(
            GoogleAPI, '_geocode_address',
            return_value={'lat': 25.033, 'lng': 121.564}
        )

        mock_response = MagicMock()
        mock_response.json.return_value = self._mock_nearby_response()
        mock_response.raise_for_status = MagicMock()
        mocker.patch('integrations.google.api.requests.get', return_value=mock_response)

        result = GoogleAPI.search_nearby_coffee_shops(address='台北市信義區')

        mock_geocode.assert_called_once_with('台北市信義區')
        assert len(result) == 3

    def test_geocode_fails(self, mocker):
        """地址轉換失敗回傳空列表"""
        mocker.patch.object(GoogleAPI, '_geocode_address', return_value={})

        result = GoogleAPI.search_nearby_coffee_shops(address='不存在的地址')

        assert result == []

    def test_timeout(self, mocker):
        """請求逾時回傳空列表"""
        mocker.patch('integrations.google.api.requests.get', side_effect=Timeout)

        result = GoogleAPI.search_nearby_coffee_shops(lat=25.033, lng=121.564)

        assert result == []

    def test_request_exception(self, mocker):
        """請求失敗回傳空列表"""
        mocker.patch('integrations.google.api.requests.get', side_effect=RequestException('error'))

        result = GoogleAPI.search_nearby_coffee_shops(lat=25.033, lng=121.564)

        assert result == []

    def test_status_not_ok(self, mocker):
        """API 狀態非 OK 回傳空列表"""
        mock_response = MagicMock()
        mock_response.json.return_value = {'status': 'ZERO_RESULTS', 'results': []}
        mock_response.raise_for_status = MagicMock()
        mocker.patch('integrations.google.api.requests.get', return_value=mock_response)

        result = GoogleAPI.search_nearby_coffee_shops(lat=25.033, lng=121.564)

        assert result == []

    def test_max_ten_results(self, mocker):
        """最多回傳 10 筆結果"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'status': 'OK',
            'results': [
                {'place_id': f'ChIJ{i:03d}', 'name': f'咖啡店{i}', 'rating': 4.0, 'user_ratings_total': 100}
                for i in range(12)
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mocker.patch('integrations.google.api.requests.get', return_value=mock_response)

        result = GoogleAPI.search_nearby_coffee_shops(lat=25.033, lng=121.564)

        assert len(result) == 10

    def test_weighted_rating_sort_order(self, mocker):
        """驗證加權評分排序：高評分但少人評 vs 中評分但多人評"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'status': 'OK',
            'results': [
                # 高評分但只有 5 人評分 → 加權後會被拉低
                {'place_id': 'few_reviews', 'name': '少人評', 'rating': 5.0, 'user_ratings_total': 5},
                # 中評分但 1000 人評分 → 加權後更可靠
                {'place_id': 'many_reviews', 'name': '多人評', 'rating': 4.5, 'user_ratings_total': 1000},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mocker.patch('integrations.google.api.requests.get', return_value=mock_response)

        result = GoogleAPI.search_nearby_coffee_shops(lat=25.033, lng=121.564)

        # 多人評的加權評分應高於少人評
        assert result[0]['place_id'] == 'many_reviews'
        assert result[1]['place_id'] == 'few_reviews'

    def test_no_rating_uses_default(self, mocker):
        """無評分時使用預設平均評分"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'status': 'OK',
            'results': [
                {'place_id': 'ChIJ001', 'name': '無評分店'},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mocker.patch('integrations.google.api.requests.get', return_value=mock_response)

        result = GoogleAPI.search_nearby_coffee_shops(lat=25.033, lng=121.564)

        assert len(result) == 1
        assert result[0]['rating'] == 4.0  # AVERAGE_RATING 預設值
        assert result[0]['weighted_rating'] == 4.0

    def test_result_fields(self, mocker):
        """驗證回傳欄位"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'status': 'OK',
            'results': [
                {'place_id': 'ChIJ001', 'name': '測試店', 'rating': 4.5, 'user_ratings_total': 200},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mocker.patch('integrations.google.api.requests.get', return_value=mock_response)

        result = GoogleAPI.search_nearby_coffee_shops(lat=25.033, lng=121.564)

        assert 'place_id' in result[0]
        assert 'name' in result[0]
        assert 'rating' in result[0]
        assert 'weighted_rating' in result[0]


class TestIsWithinServiceArea:
    """測試 GoogleAPI._is_within_service_area"""

    def test_taipei_center_is_within(self):
        assert GoogleAPI._is_within_service_area(25.033, 121.564) is True

    def test_keelung_is_within(self):
        assert GoogleAPI._is_within_service_area(25.128, 121.740) is True

    def test_new_taipei_is_within(self):
        assert GoogleAPI._is_within_service_area(25.012, 121.465) is True

    def test_taichung_is_outside(self):
        assert GoogleAPI._is_within_service_area(24.147, 120.673) is False

    def test_australia_is_outside(self):
        assert GoogleAPI._is_within_service_area(-33.868, 151.209) is False


class TestSearchCoffeeShopsServiceArea:
    """測試 search_coffee_shops 的服務範圍過濾"""

    def test_filters_out_results_outside_service_area(self, mocker):
        """台北以外的結果被過濾掉"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'status': 'OK',
            'results': [
                {'name': '台北店', 'place_id': 'ChIJ001', 'geometry': {'location': {'lat': 25.033, 'lng': 121.564}}},
                {'name': '台中店', 'place_id': 'ChIJ002', 'geometry': {'location': {'lat': 24.147, 'lng': 120.673}}},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mocker.patch('integrations.google.api.requests.get', return_value=mock_response)

        result = GoogleAPI.search_coffee_shops('咖啡')

        assert len(result) == 1
        assert result[0]['place_id'] == 'ChIJ001'

    def test_returns_empty_when_all_results_outside_service_area(self, mocker):
        """全部結果都在範圍外時回傳空列表"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'status': 'OK',
            'results': [
                {'name': '澳洲店', 'place_id': 'ChIJ001', 'geometry': {'location': {'lat': -33.868, 'lng': 151.209}}},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mocker.patch('integrations.google.api.requests.get', return_value=mock_response)

        result = GoogleAPI.search_coffee_shops('咖啡')

        assert result == []

    def test_result_without_geometry_is_filtered_out(self, mocker):
        """沒有 geometry 的結果被過濾掉"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'status': 'OK',
            'results': [
                {'name': '無座標店', 'place_id': 'ChIJ001'},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mocker.patch('integrations.google.api.requests.get', return_value=mock_response)

        result = GoogleAPI.search_coffee_shops('咖啡')

        assert result == []


class TestSearchNearbyCoffeeShopsServiceArea:
    """測試 search_nearby_coffee_shops 的服務範圍驗證"""

    def test_raises_out_of_service_area_error_for_taichung(self):
        """台中座標直接拋出 OutOfServiceAreaError"""
        import pytest
        with pytest.raises(OutOfServiceAreaError):
            GoogleAPI.search_nearby_coffee_shops(lat=24.147, lng=120.673)

    def test_raises_out_of_service_area_error_when_geocode_returns_outside_area(self, mocker):
        """geocode 回傳的座標在範圍外時拋出 OutOfServiceAreaError"""
        import pytest
        mocker.patch.object(
            GoogleAPI, '_geocode_address',
            return_value={'lat': 24.147, 'lng': 120.673}
        )

        with pytest.raises(OutOfServiceAreaError):
            GoogleAPI.search_nearby_coffee_shops(address='台中市中區')
