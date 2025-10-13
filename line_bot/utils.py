import os
import time
import requests


GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
BASE_URL = 'https://maps.googleapis.com/maps/api/place'

def get_get_coffee_shop_detail(name:str)->dict:

    textsearch_url = f'{BASE_URL}/textsearch/json'
    params = {
        'query': f'{name} 咖啡店',
        'type': 'cafe',
        'key': GOOGLE_API_KEY,
    }

    response = requests.get(textsearch_url, params=params)
    print(response.json())
