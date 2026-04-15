import logging

from django.db.models import F
from django.utils import timezone

from integrations.models import ApiUsageRecord

logger = logging.getLogger(__name__)


class ApiUsageService:

    @staticmethod
    def _get_year_month():
        return timezone.now().strftime('%Y-%m')

    @staticmethod
    def _increment_usage(user_id, field_name):
        year_month = ApiUsageService._get_year_month()
        record, _ = ApiUsageRecord.objects.get_or_create(
            user_id=user_id,
            year_month=year_month,
        )
        ApiUsageRecord.objects.filter(pk=record.pk).update(
            **{field_name: F(field_name) + 1},
            total_api_calls=F('total_api_calls') + 1,
        )
        logger.info(f'User {user_id} {field_name} +1 ({year_month})')

    @staticmethod
    def check_can_use(user_id):
        """檢查使用者本月是否還有 API 額度"""
        year_month = ApiUsageService._get_year_month()
        record, _ = ApiUsageRecord.objects.get_or_create(
            user_id=user_id,
            year_month=year_month,
        )
        return record.check_limit()

    @staticmethod
    def increment_detail_calls(user_id):
        """遞增 detail API 呼叫次數（get_shop_detail）"""
        ApiUsageService._increment_usage(user_id, 'detail_calls')

    @staticmethod
    def increment_search_calls(user_id):
        """遞增 search API 呼叫次數（search_coffee_shops / search_nearby）"""
        ApiUsageService._increment_usage(user_id, 'search_calls')
