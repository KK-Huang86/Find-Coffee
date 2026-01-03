import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from cafe.models import Cafe, CafeNomadCache, CafeAttributeVote

logger = logging.getLogger(__name__)


class CafeAttributeMatcher:
    """
    跟第三方API CafeNomad 存取的資料進行比對
    """

    # 誤差值為 55 公尺
    COORDINATE_TOLERANCE = Decimal('0.0005')

    @classmethod
    def match_and_sync_attributes(cls, cafe: Cafe) -> bool:
        """
        檢查 Cafe 的資料

        Args:
            cafe: Cafe 實例

        Returns:
            bool: 是否有資料被更新
        """
        # 1. 检查是否需要同步
        needs_socket = cafe.has_socket is None
        needs_limited_time = cafe.limited_time is None

        if not needs_socket and not needs_limited_time:
            # 已經有資料
            return False

        # 2. 檢查該Cafe 的實例是否有經緯度
        if cafe.lat is None or cafe.lng is None:
            logger.debug(f'Cafe {cafe.place_id} 缺少經緯度，跳過')
            return False

        # 3. 比對 CafeNomadCache(從 CafeNomad 抓下來的資料)
        matched_cache = cls._find_nearby_cache(cafe.lat, cafe.lng)

        if not matched_cache:
            logger.debug(f'Cafe {cafe.place_id} 該經緯度未成功比對 CafeNomad 裡的資料 ')
            return False

        # 4. 同步属性 Cafe 跟 CafeAttributeVote 的相關資料
        updated = cls._sync_attributes(cafe, matched_cache, needs_socket, needs_limited_time)

        return updated

    @classmethod
    def _find_nearby_cache(cls, lat: Decimal, lng: Decimal) -> CafeNomadCache:
        """
        根據 Cafe 的經緯度去比對 CafeNomadCache

        Args:
            lat: 緯度
            lng: 經度

        Returns:
            CafeNomadCache 或 None
        """
        lat_min = lat - cls.COORDINATE_TOLERANCE
        lat_max = lat + cls.COORDINATE_TOLERANCE
        lng_min = lng - cls.COORDINATE_TOLERANCE
        lng_max = lng + cls.COORDINATE_TOLERANCE

        # 查詢符合範圍經緯度的咖啡店，返回第一筆
        return CafeNomadCache.objects.filter(
            lat__gte=lat_min,
            lat__lte=lat_max,
            lng__gte=lng_min,
            lng__lte=lng_max,
        ).order_by('-synced_at').first()

    @classmethod
    def _sync_attributes(
        cls,
        cafe: Cafe,
        cache: CafeNomadCache,
        sync_socket: bool,
        sync_limited_time: bool
    ) -> bool:
        """
        同步相關資訊

        Returns:
            bool: 是否有成功更新
        """

        updated = False
        update_fields = []

        with transaction.atomic():
            # 同步插座與否
            if sync_socket and cache.socket:
                cafe.has_socket = cache.socket
                cls._create_vote_record(cafe, 'socket', cache.socket)
                updated = True
                update_fields.append('has_socket')
                logger.info(f'Cafe {cafe.place_id} 同步插座資料: {cache.socket}')

            # 同步限時與否
            if sync_limited_time and cache.limited_time:
                cafe.limited_time = cache.limited_time
                cls._create_vote_record(cafe, 'limited_time', cache.limited_time)
                updated = True
                update_fields.append('limited_time')
                logger.info(f'Cafe {cafe.place_id} 同步限時資料: {cache.limited_time}')

            # 更新 Cafe 的資料
            if updated:
                cafe.attributes_last_calculated_at = timezone.now()
                update_fields.extend(['attributes_last_calculated_at', 'updated_at'])
                cafe.save(update_fields=update_fields)

        return updated

    @classmethod
    def _create_vote_record(cls, cafe: Cafe, attribute: str, value: str):
        """
        創建 CafeAttributeVote ，
        """
        CafeAttributeVote.objects.create(
            cafe=cafe,
            user=None,  # cafenomad 的資料來源
            attribute=attribute,
            value=value,
            source='cafenomad'
        )
