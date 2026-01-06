"""
Postback Action Handlers - 每個 action 獨立處理
"""
import logging

from cafe.models import Cafe
from integrations.google.api import GoogleAPI
from line_bot.builders.flex_builder import LineMessageBuilder, QuickReplyBuilder
from line_bot.handlers.helpers import get_or_create_cafe_info, reply_text, reply_cafe_detail
from line_bot.services.search_cache import SearchHistoryService
from users.views import FavoritesManager

logger = logging.getLogger(__name__)


def handle_favorite(line_bot_api, reply_token, user, params):
    """處理收藏動作"""
    place_id = params.get('place_id')

    info_d, _ = get_or_create_cafe_info(place_id)
    if not info_d:
        reply_text(line_bot_api, reply_token, '找不到該咖啡店')
        return

    ok, msg = FavoritesManager.add_favorite(user, info_d)
    reply_text(line_bot_api, reply_token, msg)


def handle_unfavorite(line_bot_api, reply_token, user, params):
    """處理取消收藏動作"""
    place_id = params.get('place_id')

    cafe = Cafe.objects.filter(place_id=place_id).first()
    if not cafe:
        reply_text(line_bot_api, reply_token, '找不到該咖啡店，無法取消收藏')
        return

    info_d = cafe.to_dict()
    ok, msg = FavoritesManager.remove_favorite(user, info_d)
    reply_text(line_bot_api, reply_token, msg)


def handle_view_detail(line_bot_api, reply_token, user, params):
    """處理查看詳情動作"""
    place_id = params.get('place_id')

    info_d, cafe = get_or_create_cafe_info(place_id)
    if not info_d:
        reply_text(line_bot_api, reply_token, '找不到此咖啡店')
        return

    is_favorited = False
    if cafe:
        is_favorited = user.favorites.filter(cafe=cafe).exists()

    reply_cafe_detail(line_bot_api, reply_token, info_d, is_favorited)


def handle_recent_search(line_bot_api, reply_token, user, params):
    """處理最近搜尋動作"""
    search_type = params.get('type')
    keyword = params.get('keyword')
    place_id = params.get('place_id')
    user_id = user.line_user_id

    if not keyword:
        logger.warning(f'Recent search without keyword: {params}')
        return

    if search_type == 'shop_name':
        _handle_shop_name_search(line_bot_api, reply_token, user, user_id, keyword, place_id)

    elif search_type == 'address':
        _handle_address_search(line_bot_api, reply_token, user, user_id, keyword)


def _handle_shop_name_search(line_bot_api, reply_token, user, user_id, keyword, place_id=None):
    """處理店名搜尋"""

    # 1. 若有 place_id 直接取用。近期查詢該資料只有一筆時，才會存 place_id，否則為 None
    if place_id:
        cafe = Cafe.objects.filter(place_id=place_id).first()
        if cafe:
            info_d = cafe.to_dict()
            is_favorited = user.favorites.filter(cafe=cafe).exists()
            reply_cafe_detail(line_bot_api, reply_token, info_d, is_favorited)
            return

    # 2. 若沒有 place_id，檢查 DB 是否有此店家，搜尋的時候可能不只有一間
    cafes = Cafe.objects.filter(name__icontains=keyword)[:5]

    if cafes.exists():
        # DB 有資料，顯示 carousel（理論上這裡抓到的都是兩筆以上的資料，因為一筆的話會有 place_id）
        shops = [{'place_id': cafe.place_id} for cafe in cafes]

    # 3. 都沒有的話直接打 Google API 進行查詢
    else:
        shops = GoogleAPI.search_coffee_shops(keyword)

    LineMessageBuilder.send_shop_result(
        line_bot_api,
        reply_token,
        shops,
        user,
        quick_reply=QuickReplyBuilder.create_search_again_actions()
    )


def _handle_address_search(line_bot_api, reply_token, user, user_id, keyword):
    """處理地址搜尋"""
    shops = GoogleAPI.search_nearby_coffee_shops(address=keyword)

    LineMessageBuilder.send_shop_result(
        line_bot_api,
        reply_token,
        shops,
        user,
        quick_reply=QuickReplyBuilder.create_carousel_pagination_actions()
    )


# Action Dispatch Table
ACTION_HANDLERS = {
    'favorite': handle_favorite,
    'unfavorite': handle_unfavorite,
    'view_detail': handle_view_detail,
    'recent_search': handle_recent_search,
}
