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
    def _try_increment_usage(user_id, field_name):
        year_month = ApiUsageService._get_year_month()
        record, _ = ApiUsageRecord.objects.get_or_create(
            user_id=user_id,
            year_month=year_month,
        )
        updated_count = ApiUsageRecord.objects.filter(
            pk=record.pk,
            can_use=True,
            total_api_calls__lt=F('monthly_limit'),
        ).update(
            **{field_name: F(field_name) + 1},
            total_api_calls=F('total_api_calls') + 1,
        )
        if updated_count == 0:
            ApiUsageRecord.objects.filter(pk=record.pk, can_use=True).update(can_use=False)
            return False
        logger.info(f'User {user_id} {field_name} +1 ({year_month})')
        return True

    @staticmethod
    def try_increment_detail_calls(user_id):
        """嘗試遞增 detail API 呼叫次數，超過額度回傳 False"""
        return ApiUsageService._try_increment_usage(user_id, 'detail_calls')

    @staticmethod
    def try_increment_search_calls(user_id):
        """嘗試遞增 search API 呼叫次數，超過額度回傳 False"""
        return ApiUsageService._try_increment_usage(user_id, 'search_calls')
