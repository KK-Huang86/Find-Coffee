
import requests
from decimal import Decimal
from django.core.management.base import BaseCommand
from cafe.models import CafeNomadCache


class Command(BaseCommand):
    help = '從 CafeNomad API 匯入咖啡店資料'

    def handle(self, *args, **options):
        self.stdout.write(' 開始匯入 CafeNomad 資料...')

        try:
            # 打 API
            response = requests.get('https://cafenomad.tw/api/v1.2/cafes/taipei', timeout=30)
            response.raise_for_status()
            cafes = response.json()

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'API 請求失敗: {e}'))
            return

        created_count = 0
        updated_count = 0
        skipped_count = 0

        for cafe_data in cafes:
            # 檢查必要欄位
            if not cafe_data.get('latitude') or not cafe_data.get('longitude'):
                skipped_count += 1
                continue

            try:
                # 轉換座標
                lat = Decimal(cafe_data['latitude'])
                lng = Decimal(cafe_data['longitude'])

                # 處理空字串
                def clean_value(value):
                    """空字串轉 None"""
                    return None if value == '' else value

                # 處理評分欄位（可能是 0 或空字串）
                def clean_score(value):
                    """0 或空字串轉 None"""
                    if value == '' or value == 0:
                        return None
                    return float(value) if value else None

                # 建立或更新
                obj, created = CafeNomadCache.objects.update_or_create(
                    cafenomad_id=cafe_data['id'],
                    defaults={
                        # 基本資訊
                        'name': cafe_data['name'],
                        'city': cafe_data.get('city', ''),
                        'lat': lat,
                        'lng': lng,
                        'address': cafe_data.get('address', ''),

                        # 核心屬性
                        'socket': clean_value(cafe_data.get('socket')),
                        'limited_time': clean_value(cafe_data.get('limited_time')),
                        'standing_desk': clean_value(cafe_data.get('standing_desk')),

                        # 評分欄位
                        'wifi': clean_score(cafe_data.get('wifi')),
                        'seat': clean_score(cafe_data.get('seat')),
                        'quiet': clean_score(cafe_data.get('quiet')),
                        'tasty': clean_score(cafe_data.get('tasty')),
                        'cheap': clean_score(cafe_data.get('cheap')),
                        'music': clean_score(cafe_data.get('music')),

                        # 其他資訊
                        'url': cafe_data.get('url', ''),
                        'mrt': cafe_data.get('mrt', ''),
                        'open_time': cafe_data.get('open_time', ''),
                    }
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f'處理失敗: {cafe_data.get("name")} - {e}')
                )
                skipped_count += 1

        # 結果報告
        self.stdout.write(
            self.style.SUCCESS(
                f'\n匯入完成！\n'
                f'   新增: {created_count} 筆\n'
                f'   更新: {updated_count} 筆\n'
                f'   跳過: {skipped_count} 筆'
            )
        )
