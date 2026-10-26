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
"""
import os
import sys

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

if settings.DATABASES['default']['NAME'] != 'find_coffee_loadtest':
    sys.exit(f'拒絕執行：目前資料庫為 {settings.DATABASES["default"]["NAME"]}，只能在 find_coffee_loadtest 執行')
if SCENARIO not in ('cached', 'stale', 'expired_photo'):
    sys.exit(f'未知情境: {SCENARIO}')


def cafe_fields(group, index):
    place_id = f'lt_{SCENARIO}_{group:04d}_{index:02d}'
    base = {
        'place_id': place_id,
        'name': f'LT-{SCENARIO}-{group:04d}-{index:02d}',
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
    if SCENARIO == 'cached':
        base.update(last_refreshed=now, photo_reference=f'fresh_{place_id}',
                    photo_s3_url=f'https://cdn.example.com/{place_id}.jpg', photo_updated_at=now)
    elif SCENARIO == 'stale':
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
    Cafe.objects.bulk_create([
        Cafe(**cafe_fields(group, index))
        for group in range(GROUPS)
        for index in range(SHOPS_PER_GROUP)
    ])

print(f'seeded scenario={SCENARIO} groups={GROUPS} shops_per_group={SHOPS_PER_GROUP}')
