from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)


class SearchHistoryService:
    """
    管理使用者搜尋歷史（Cache）
    """
    CACHE_KEY_PREFIX = 'search_history'
    MAX_HISTORY = 5
    CACHE_TTL = 3600 * 24 * 7  # 保留 7 天

    @staticmethod
    def add_search(user_id, keyword, search_type='shop_name'):
        """
        記錄搜尋關鍵字到 Redis

        Args:
            user_id: LINE 使用者 ID
            keyword: 搜尋關鍵字（店名或路名）
            search_type: 搜尋類型 ('shop_name' 或 'address')
        """
        try:
            key = f'{SearchHistoryService.CACHE_KEY_PREFIX}:{user_id}'

            # 取得現有歷史
            history = cache.get(key, [])

            # 建立新記錄
            new_record = {
                'keyword': keyword,
                'type': search_type,
            }

            # 移除重複的關鍵字（避免同樣的關鍵字出現兩次）
            history = [h for h in history if h['keyword'] != keyword]

            # 加到最前面
            history.insert(0, new_record)

            # 只保留最近 5 筆
            history = history[:SearchHistoryService.MAX_HISTORY]

            # 存回 cache
            cache.set(key, history, timeout=SearchHistoryService.CACHE_TTL)

            logger.info(f"User {user_id} searched: {keyword} ({search_type})")
            return True

        except Exception as e:
            logger.error(f"Failed to save search history: {e}")
            return False

    @staticmethod
    def get_search_history(user_id):

        """
        取得使用者搜尋歷史

        Returns:
            list: [{'keyword': '星巴克', 'type': 'shop_name'}, ...]
        """
        try:
            key = f'{SearchHistoryService.CACHE_KEY_PREFIX}:{user_id}'
            history = cache.get(key, [])
            return history
        except Exception as e:
            logger.error(f"Failed to get search history: {e}")
            return []

    @staticmethod
    def clear_history(user_id):
        """清除使用者搜尋歷史"""
        try:
            key = f'{SearchHistoryService.CACHE_KEY_PREFIX}:{user_id}'
            cache.delete(key)
            return True
        except Exception as e:
            logger.error(f"Failed to clear search history: {e}")
            return False
