import logging

from linebot.v3.messaging import (
    MessagingApi,
    ShowLoadingAnimationRequest,
)

logger = logging.getLogger(__name__)


def parse_opening_hours(opening_hours_l):
    """
    將 Google Places API 的營業時間列表轉換為字典

    Args:
        opening_hours_l: List[str] 例如 ['星期一: 12:00 – 18:00', ...]

    Returns:
        dict: {'星期一': '12:00 – 18:00', ...}
    """
    if not opening_hours_l:
        return {}

    hours_dict = {}
    for opening_hour in opening_hours_l:
        if ': ' in opening_hour:
            day, time = opening_hour.split(': ', 1)
            hours_dict[day] = time.strip()

    return hours_dict


def show_loading(line_bot_api: MessagingApi, user_id: str):
    """顯示打字中動畫"""
    try:
        line_bot_api.show_loading_animation(
            ShowLoadingAnimationRequest(chat_id=user_id)
        )
    except Exception as e:
        logger.warning(f'user {user_id} show_loading failed: {e}')
