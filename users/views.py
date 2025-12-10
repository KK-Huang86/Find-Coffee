# Create your views here.

import logging

from django.db import transaction, IntegrityError

from line_bot.utils import parse_opening_hours
from cafe.models import Cafe, Favorite

logger = logging.getLogger(__name__)


#TODO:好友、每一個使用的次數



class FavoritesManager:

    @staticmethod
    def add_favorite(user, info):

        if not info.get('place_id') or not info.get('name'):
            return False, '咖啡店資訊不完整'

        opening_hours_d = parse_opening_hours(info.get('opening_hours', []))

        try:
            with transaction.atomic():
                # 取得或建立咖啡店
                cafe, cafe_created = Cafe.objects.get_or_create(
                    place_id=info['place_id'],
                    defaults={
                        'name': info.get('name', '未命名咖啡店'),
                        'address': info.get('address', ''),
                        'phone': info.get('phone', ''),
                        'lat': info.get('lat'),
                        'lng': info.get('lng'),
                        'rating': info.get('rating'),
                        'user_ratings_total': info.get('user_ratings_total', 0),
                        'google_maps': info.get('google_maps', ''),
                        'website': info.get('website', ''),
                        'opening_hours': opening_hours_d
                    }
                )

                if cafe_created:
                    logger.info(f'建立新咖啡店: {cafe.name} ({cafe.place_id})')

                # 建立收藏關聯
                favorite, created = Favorite.objects.get_or_create(
                    user=user,
                    cafe=cafe
                )

                if created:
                    # 增加收藏數
                    cafe.increment_favorite_count()
                    logger.info(f'使用者 {user.member_code} 收藏 {cafe.name}')
                    return True, f'✅ 已收藏「{cafe.name}」'
                else:
                    return False, f'⚠️ 「{cafe.name}」已在您的收藏清單中'

        except IntegrityError as e:
            logger.error(f'收藏失敗 (IntegrityError): {e}')
            return False, '收藏失敗，請稍後再試'

        except Exception as e:
            logger.error(f'收藏失敗: {e}')
            return False, '系統錯誤，請稍後再試'

    @staticmethod
    def remove_favorite(user, info):

        if not info.get('place_id') or not info.get('name'):
            return False, '咖啡店資訊不完整'

        try:
            with transaction.atomic():
                # 取得咖啡店
                cafe = Cafe.objects.filter(place_id=info['place_id']).first()
                if not cafe:
                    return False, '找不到該咖啡店'

                # 刪除收藏關聯
                favorite = Favorite.objects.filter(user=user, cafe=cafe).first()
                if favorite:
                    favorite.delete()
                    # 減少收藏數
                    cafe.decrement_favorite_count()
                    logger.info(f'使用者 {user.member_code} 取消收藏 {cafe.name}')
                    return True, f'已取消收藏「{cafe.name}」'
                else:
                    return False, f'「{cafe.name}」不在您的收藏清單中'

        except IntegrityError as e:
            logger.error(f'取消收藏失敗 (IntegrityError): {e}')
            return False, '取消收藏失敗，請稍後再試'

        except Exception as e:
            logger.error(f'取消收藏失敗: {e}')
            return False, '系統錯誤，請稍後再試'
