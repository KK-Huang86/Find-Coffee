import logging
from collections import Counter

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from cafe.models import Cafe, CafeAttributeVote

logger = logging.getLogger(__name__)


class VoteService:
    """處理使用者投票相關邏輯"""

    # 屬性對應的 Cafe 欄位（quiet, cheap 目前 Cafe 沒有欄位，投票會記錄但不更新 Cafe）
    ATTRIBUTE_TO_FIELD = {
        'socket': 'has_socket',
        'limited_time': 'limited_time',
        # 'quiet': 'is_quiet',   # TODO: 需要新增 Cafe 欄位
        # 'cheap': 'is_cheap',   # TODO: 需要新增 Cafe 欄位
    }

    VALID_ATTRIBUTES = {'socket', 'limited_time'}
    VALID_VALUES = {'yes', 'no', 'unknown'}

    @classmethod
    def create_user_votes(cls, cafe_id: int, user_id: int, answers: dict):
        """
        批次建立使用者投票記錄

        Args:
            cafe_id: Cafe ID
            user_id: User ID
            answers: 回答字典，如 {'socket': 'yes', 'limited_time': 'no', ...}
        """
        try:
            cafe = Cafe.objects.get(id=cafe_id)
        except Exception as e:
            logger.error(f'cant find this cafe in data , cafe id:{cafe_id}: {e}')

        with transaction.atomic():
            for attribute, value in answers.items():
                if attribute not in cls.VALID_ATTRIBUTES:
                    logger.warning(f'Unknown attribute: {attribute}, skipping')
                    continue
                if value not in cls.VALID_VALUES:
                    logger.warning(f'Invalid value: {value} for {attribute}, skipping')
                    continue
                CafeAttributeVote.objects.update_or_create(
                    cafe_id=cafe_id,
                    user_id=user_id,
                    attribute=attribute,
                    defaults={
                        'value': value,
                        'source': 'user',
                    }
                )
                logger.info(f'User {user_id} voted {attribute}={value} for Cafe {cafe_id}')

            # 投票完成後，重新聚合該咖啡店的屬性
            cls.aggregate_and_update_cafe(cafe)

    @classmethod
    def aggregate_and_update_cafe(cls, cafe: Cafe):
        """
        聚合所有投票，使用多數決更新 Cafe 屬性

        Args:
            cafe: Cafe 實例
        """
        update_fields = []

        for attribute, field_name in cls.ATTRIBUTE_TO_FIELD.items():
            # 只處理 Cafe model 有的欄位
            if not hasattr(cafe, field_name):
                continue

            # 取得該屬性的所有投票
            votes = CafeAttributeVote.objects.filter(
                cafe=cafe,
                attribute=attribute
            ).exclude(value='unknown')  # 排除「不確定」的投票

            if not votes.exists():
                continue

            # 多數決：計算每個 value 的票數
            vote_counts = votes.values('value').annotate(count=Count('id')).order_by('-count', 'value')

            if vote_counts:
                winning_value = vote_counts[0]['value']

                # 更新 Cafe 欄位
                setattr(cafe, field_name, winning_value)
                update_fields.append(field_name)
                logger.info(f'Cafe {cafe.place_id} {attribute} 更新為 {winning_value}')

        if update_fields:
            cafe.attributes_last_calculated_at = timezone.now()
            update_fields.append('attributes_last_calculated_at')
            cafe.save(update_fields=update_fields)
