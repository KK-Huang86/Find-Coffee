"""
壓測用的 Google Maps / LINE Messaging API mock server（只用標準函式庫）。

- 讓壓測完全不打到真的 Google / LINE，回應延遲以環境變數模擬：
  DETAIL_LATENCY_MS（Places Detail）、PHOTO_LATENCY_MS（Photo API）、LINE_LATENCY_MS（LINE API）、
  GEOCODE_LATENCY_MS（Geocoding）、NEARBY_LATENCY_MS（Nearby Search）
- photo_reference 以 expired_ 開頭時回 403，模擬 Google 拒絕失效的 reference
- Geocoding：地址含 LT-MISS 時回 ZERO_RESULTS（模擬查不到的地址）；其餘依地址結尾的編號回傳不同座標，
  讓每個地址對應到不同的 Nearby Search 快取 key
- Nearby Search：固定回傳 seed 的 10 間店（lt_addr_00 ~ lt_addr_09）
- GET /__stats 回傳各端點被呼叫次數；POST /__reset 歸零
"""
import json
import os
import re
import threading
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

DETAIL_LATENCY = int(os.environ.get('DETAIL_LATENCY_MS', '300')) / 1000
PHOTO_LATENCY = int(os.environ.get('PHOTO_LATENCY_MS', '150')) / 1000
LINE_LATENCY = int(os.environ.get('LINE_LATENCY_MS', '50')) / 1000
GEOCODE_LATENCY = int(os.environ.get('GEOCODE_LATENCY_MS', '200')) / 1000
NEARBY_LATENCY = int(os.environ.get('NEARBY_LATENCY_MS', '300')) / 1000
NEARBY_PLACE_IDS = [f'lt_addr_{i:02d}' for i in range(10)]
PUBLIC_BASE = os.environ.get('MOCK_PUBLIC_BASE', 'http://mock-external:8080')

stats = Counter()
stats_lock = threading.Lock()


def count(key):
    with stats_lock:
        stats[key] += 1


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass

    def _send(self, status, body=b'', content_type='application/json', headers=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def _json(self, status, data):
        self._send(status, json.dumps(data).encode())

    def _drain_body(self):
        length = int(self.headers.get('Content-Length') or 0)
        if length:
            self.rfile.read(length)

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)

        if url.path == '/__stats':
            with stats_lock:
                return self._json(200, dict(stats))

        if url.path == '/maps/api/place/details/json':
            count('google_detail')
            time.sleep(DETAIL_LATENCY)
            place_id = query.get('place_id', [''])[0]
            return self._json(200, {
                'status': 'OK',
                'result': {
                    'name': f'LT 刷新後 {place_id}',
                    'formatted_address': '台北市信義區壓測路 1 號',
                    'formatted_phone_number': '02-0000-0000',
                    'rating': 4.5,
                    'user_ratings_total': 100,
                    'geometry': {'location': {'lat': 25.03, 'lng': 121.56}},
                    'url': 'https://maps.google.com/?cid=0',
                    'website': 'https://example.com',
                    'photos': [{'photo_reference': f'fresh_{place_id}_{time.time_ns()}'}],
                    'reviews': [],
                },
            })

        if url.path == '/maps/api/geocode/json':
            count('google_geocode')
            time.sleep(GEOCODE_LATENCY)
            address = query.get('address', [''])[0]
            if 'LT-MISS' in address:
                return self._json(200, {'status': 'ZERO_RESULTS', 'results': []})
            match = re.search(r'(\d+)$', address)
            offset = int(match.group(1)) if match else 0
            # 每個編號差 0.001 度（約 110 公尺），讓不同地址落在不同的 Nearby 快取 key，且仍在服務範圍內
            return self._json(200, {
                'status': 'OK',
                'results': [{'geometry': {'location': {'lat': 25.03 + offset * 0.001, 'lng': 121.56}}}],
            })

        if url.path == '/maps/api/place/nearbysearch/json':
            count('google_nearby')
            time.sleep(NEARBY_LATENCY)
            return self._json(200, {
                'status': 'OK',
                'results': [
                    {'place_id': pid, 'name': f'LT 附近 {pid}', 'rating': 4.0 + i * 0.05, 'user_ratings_total': 100}
                    for i, pid in enumerate(NEARBY_PLACE_IDS)
                ],
            })

        if url.path == '/maps/api/place/photo':
            return self._photo(query)

        if url.path.startswith('/image/'):
            count('google_photo_image')
            return self._send(200, b'\xff\xd8\xff', content_type='image/jpeg')

        count(f'unknown GET {url.path}')
        return self._json(404, {'error': 'not mocked'})

    def do_HEAD(self):
        url = urlparse(self.path)
        if url.path == '/maps/api/place/photo':
            return self._photo(parse_qs(url.query))
        if url.path.startswith('/image/'):
            count('google_photo_image')
            return self._send(200, content_type='image/jpeg')
        count(f'unknown HEAD {url.path}')
        return self._send(404)

    def _photo(self, query):
        time.sleep(PHOTO_LATENCY)
        reference = query.get('photo_reference', [''])[0]
        if reference.startswith('expired_'):
            count('google_photo_rejected')
            return self._send(403)
        count('google_photo_ok')
        return self._send(302, headers={'Location': f'{PUBLIC_BASE}/image/{reference}.jpg'})

    def do_POST(self):
        url = urlparse(self.path)
        self._drain_body()

        if url.path == '/__reset':
            with stats_lock:
                stats.clear()
            return self._json(200, {})

        if url.path == '/v2/bot/message/reply':
            count('line_reply')
            time.sleep(LINE_LATENCY)
            # line-bot-sdk 會驗證回應：sentMessages 至少要有一筆
            return self._json(200, {'sentMessages': [{'id': '1', 'quoteToken': 'q'}]})

        if url.path == '/v2/bot/chat/loading/start':
            count('line_loading')
            time.sleep(LINE_LATENCY)
            return self._json(202, {})

        count(f'unknown POST {url.path}')
        return self._json(404, {'error': 'not mocked'})


if __name__ == '__main__':
    server = ThreadingHTTPServer(('0.0.0.0', 8080), Handler)
    server.daemon_threads = True
    print(
        f'mock server on :8080 (detail={DETAIL_LATENCY}s, photo={PHOTO_LATENCY}s, line={LINE_LATENCY}s, '
        f'geocode={GEOCODE_LATENCY}s, nearby={NEARBY_LATENCY}s)',
        flush=True,
    )
    server.serve_forever()
