"""
壓測資料準備（只在 find_coffee_loadtest 資料庫執行）。

每次執行會清掉上一輪的壓測資料再重建，確保每個情境的起始狀態一致：
- 使用者 U-loadtest-0000 ~：每個 iteration 用不同使用者，避免 2 秒的使用者 lock 讓請求被節流
- 每個 iteration 搜尋一組 10 間店（店名前綴 LT-<scenario>-<group>-），組與組之間不重疊，
  因為過期店家刷新後就不再過期，同一組不能重複使用

情境：
- cached：資料未過期、已有 S3 照片 → 不呼叫任何外部 API（基準線）
- stale：資料從未刷新、沒有 S3 照片 → 回覆前同步刷新 10 間 + 解析 10 張照片
- expired_photo：資料未過期、photo_reference 已失效、沒有 S3 照片 → 照片 403 → 刷新 → 用新 reference 重試

地址搜尋情境（驗證 Google 搜尋共用快取）：mock Nearby Search 固定回傳 lt_addr_00 ~ 09 這 10 間店，
seed 為已快取狀態，讓量到的只有 Geocoding + Nearby Search 的差異
- address_cold：每個 iteration 搜尋不同地址 → 每次都未命中（等同沒有快取時的成本）
- address_hot：所有 iteration 搜尋同一個地址 → 只有第一次打 Google，同時進來的請求等鎖（擊穿防護）
- address_miss：所有 iteration 搜尋同一個查不到的地址 → 空結果被快取（穿透防護）

雪崩防護情境：
- refresh_spread：所有店家在同一時間匯入（last_refreshed = now - AGE_HOURS），已有 S3 照片；
  依 AGE_HOURS 量測有幾間店被判定過期而同步刷新，驗證過期門檻分散在 25～30 天
"""
import os
import sys
from datetime import timedelta

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.conf import settings  # noqa: E402
from django.db import transaction  # noqa: E402
from django.utils import timezone  # noqa: E402

from cafe.models import Cafe  # noqa: E402
from users.models import User  # noqa: E402

SCENARIO = os.environ['SCENARIO']
GROUPS = int(os.environ.get('GROUPS', '30'))
SHOPS_PER_GROUP = int(os.environ.get('SHOPS_PER_GROUP', '10'))
AGE_HOURS = float(os.environ.get('AGE_HOURS', '0'))

if settings.DATABASES['default']['NAME'] != 'find_coffee_loadtest':
    sys.exit(f'拒絕執行：目前資料庫為 {settings.DATABASES["default"]["NAME"]}，只能在 find_coffee_loadtest 執行')
ADDRESS_SCENARIOS = ('address_cold', 'address_hot', 'address_miss')
if SCENARIO not in ('cached', 'stale', 'expired_photo', 'refresh_spread') + ADDRESS_SCENARIOS:
    sys.exit(f'未知情境: {SCENARIO}')


def cafe_fields(group, index):
    place_id = f'lt_{SCENARIO}_{group:04d}_{index:02d}'
    return _cafe(place_id, f'LT-{SCENARIO}-{group:04d}-{index:02d}', SCENARIO)


def _cafe(place_id, name, state):
    base = {
        'place_id': place_id,
        'name': name,
        'address': '台北市信義區壓測路 1 號',
        'phone': '02-0000-0000',
        'lat': 25.03,
        'lng': 121.56,
        'rating': 4.2,
        'user_ratings_total': 10,
        'opening_hours': {},
        'reviews': [],
        'ai_summary': '壓測摘要',
        'has_socket': True,
        'limited_time': False,
    }
    now = timezone.now()
    if state == 'cached':
        base.update(last_refreshed=now, photo_reference=f'fresh_{place_id}',
                    photo_s3_url=f'https://cdn.example.com/{place_id}.jpg', photo_updated_at=now)
    elif state == 'refresh_spread':
        # 同一批匯入：所有店家 last_refreshed 相同；已有 S3 照片，量到的外部呼叫只有過期刷新的 Places Detail
        base.update(last_refreshed=now - timedelta(hours=AGE_HOURS), photo_reference=f'fresh_{place_id}',
                    photo_s3_url=f'https://cdn.example.com/{place_id}.jpg', photo_updated_at=now)
    elif state == 'stale':
        base.update(last_refreshed=None, photo_reference=f'expired_{place_id}', photo_s3_url='')
    else:
        base.update(last_refreshed=now, photo_reference=f'expired_{place_id}', photo_s3_url='')
    return base


with transaction.atomic():
    Cafe.objects.filter(place_id__startswith='lt_').delete()
    User.objects.filter(line_user_id__startswith='U-loadtest-').delete()

    User.objects.bulk_create([
        User(line_user_id=f'U-loadtest-{i:04d}', member_code=f'LT{i:06d}', display_name=f'loadtest {i}')
        for i in range(GROUPS)
    ])
    if SCENARIO in ADDRESS_SCENARIOS:
        Cafe.objects.bulk_create([
            Cafe(**_cafe(f'lt_addr_{index:02d}', f'LT-addr-{index:02d}', 'cached'))
            for index in range(10)
        ])
    else:
        Cafe.objects.bulk_create([
            Cafe(**cafe_fields(group, index))
            for group in range(GROUPS)
            for index in range(SHOPS_PER_GROUP)
        ])

print(f'seeded scenario={SCENARIO} groups={GROUPS} shops_per_group={SHOPS_PER_GROUP}')
