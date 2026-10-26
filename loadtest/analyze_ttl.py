"""
讀取壓測 Redis（db 2）中 Google 搜尋快取 key 的剩餘 TTL，分析過期時間分布，驗證 TTL 隨機偏移（防雪崩）。

在 web-loadtest container 內執行：uv run --no-sync python loadtest/analyze_ttl.py
"""
import json
import os

import redis

BASE_TTL = {
    'geocode': 7 * 24 * 60 * 60,
    'nearby': 24 * 60 * 60,
}
WINDOW_SECONDS = 60


def max_in_window(values, window):
    """排序後以雙指標找出任一 window 秒內最多有幾個值"""
    values = sorted(values)
    best = left = 0
    for right, value in enumerate(values):
        while value - values[left] >= window:
            left += 1
        best = max(best, right - left + 1)
    return best


def analyze(client, namespace, base):
    keys = list(client.scan_iter(match=f'*google:v1:{namespace}:*', count=1000))
    ttls = [t for t in (client.ttl(k) for k in keys) if t > 0]
    if not ttls:
        return {'keys': 0}
    buckets = {}
    for t in ttls:
        # 以基準 TTL 的 1% 為一格（例如 24 小時 → 約 14.4 分鐘）
        bucket = round(t / base * 100)
        buckets[bucket] = buckets.get(bucket, 0) + 1
    return {
        'keys': len(ttls),
        'base_ttl_seconds': base,
        'min_ttl_seconds': min(ttls),
        'max_ttl_seconds': max(ttls),
        'min_ratio': round(min(ttls) / base, 4),
        'max_ratio': round(max(ttls) / base, 4),
        'expiry_spread_seconds': max(ttls) - min(ttls),
        f'max_keys_expiring_within_{WINDOW_SECONDS}s': max_in_window(ttls, WINDOW_SECONDS),
        'histogram_percent_of_base': dict(sorted(buckets.items())),
    }


if __name__ == '__main__':
    client = redis.Redis.from_url(os.environ['REDIS_URL'])
    print(json.dumps({ns: analyze(client, ns, base) for ns, base in BASE_TTL.items()}, ensure_ascii=False, indent=2))
