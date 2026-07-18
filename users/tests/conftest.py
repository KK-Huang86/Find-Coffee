import pytest


@pytest.fixture
def user_data():
    """測試用的 User 資料"""
    return {
        'line_user_id': 'U12345678901234567890123456789012',
        'display_name': '測試使用者',
        'member_type': 1,
        'status': 1,
    }


@pytest.fixture
def cafe_info():
    """測試用的咖啡店資訊"""
    return {
        'place_id': 'ChIJ123456789',
        'name': '測試咖啡店',
        'address': '台北市信義區信義路五段7號',
        'phone': '02-1234-5678',
        'lat': 25.033964,
        'lng': 121.564468,
        'rating': 4.5,
        'user_ratings_total': 200,
        'google_maps': 'https://maps.google.com/xxx',
        'website': 'https://example.com',
        'opening_hours': ['星期一: 09:00 – 18:00', '星期二: 09:00 – 18:00'],
    }
