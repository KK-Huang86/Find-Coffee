"""
Postback Action Handlers - 每個 action 獨立處理
"""
import logging

from linebot.v3.messaging import ReplyMessageRequest, TextMessage

from cafe.models import Cafe
from integrations.google.api import GoogleAPI
from line_bot.builders.flex_builder import LineMessageBuilder, QuickReplyBuilder, FavoritesMessageBuilder
from line_bot.constants import UserState, MenuAction
from line_bot.handlers.helpers import get_or_create_cafe_info, reply_text, reply_cafe_detail
from line_bot.services.search_cache import SearchHistoryService
from line_bot.state import set_state
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
    user_id = user.line_user_id

    if not keyword:
        logger.warning(f'Recent search without keyword: {params}')
        return

    if search_type == 'shop_name':
        _handle_shop_name_search(line_bot_api, reply_token, user, user_id, keyword)

    elif search_type == 'address':
        _handle_address_search(line_bot_api, reply_token, user, user_id, keyword)


def _handle_shop_name_search(line_bot_api, reply_token, user, user_id, keyword):
    """處理店名搜尋"""
    SearchHistoryService.add_search(user_id, keyword, 'shop_name')
    # 先檢查 DB 是否有此店家，搜尋的時候可能不只有一間
    cafes = Cafe.objects.filter(name__icontains=keyword)[:5]

    if len(cafes) == 1:
        # 只有一筆結果，直接顯示詳情，postback
        cafe = cafes[0]
        info_d = cafe.to_dict()
        is_favorited = user.favorites.filter(cafe=cafe).exists()
        reply_cafe_detail(line_bot_api, reply_token, info_d, is_favorited)
        return

    elif cafes.exists():
        # DB 有多筆資料，顯示 carousel 讓使用者選擇
        shops = [{'place_id': cafe.place_id} for cafe in cafes]
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
    SearchHistoryService.add_search(user_id, keyword, 'address')

    LineMessageBuilder.send_shop_result(
        line_bot_api,
        reply_token,
        shops,
        user,
        quick_reply=QuickReplyBuilder.create_carousel_pagination_actions()
    )



def _menu_search_shop_name(line_bot_api, reply_token, user):
    """處理店名查詢"""
    set_state(user.line_user_id, UserState.WAITING_SHOP_NAME)
    reply_text(line_bot_api, reply_token, '請輸入咖啡店名稱 ☕️')


def _menu_search_address(line_bot_api, reply_token, user):
    """處理路名查詢"""
    set_state(user.line_user_id, UserState.WAITING_ADDRESS)
    reply_text(line_bot_api, reply_token, '請輸入路名️（例如：台北市信義區松信路）')


def _menu_share_location(line_bot_api, reply_token, user):
    """處理分享位置"""
    quick_reply = QuickReplyBuilder.create_location_request()
    line_bot_api.reply_message(
        ReplyMessageRequest(
            reply_token=reply_token,
            messages=[
                TextMessage(
                    text='請點擊下方按鈕分享您的位置\n我來幫您找附近的咖啡店 ☕️',
                    quick_reply=quick_reply
                )
            ]
        )
    )


def _menu_favorites(line_bot_api, reply_token, user):
    """處理收藏清單"""
    user_id = user.line_user_id
    favorite_count = user.favorites.count()

    if favorite_count == 0:
        message = TextMessage(text='您還沒有收藏任何咖啡店喔～\n快去探索喜歡的店家吧！❤️')
    elif favorite_count <= 5:
        message = FavoritesMessageBuilder.show_favorites_carousel(user_id)
    else:
        message = FavoritesMessageBuilder.show_favorites_list(user_id)

    line_bot_api.reply_message(
        ReplyMessageRequest(reply_token=reply_token, messages=[message])
    )


def _menu_recent_search(line_bot_api, reply_token, user):
    """處理最近查詢"""
    user_id = user.line_user_id
    quick_reply = QuickReplyBuilder.create_recent_search_quick_reply(user_id)

    if quick_reply:
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[
                    TextMessage(text='請選擇最近搜尋的關鍵字：', quick_reply=quick_reply)
                ]
            )
        )
    else:
        reply_text(line_bot_api, reply_token, '目前還沒有搜尋紀錄喔～')


def _menu_more_info(line_bot_api, reply_token, user):
    """處理更多資訊，後續開發中"""
    reply_text(line_bot_api, reply_token, '更多資訊功能開發中...')


# Menu Dispatch Table
MENU_HANDLERS = {
    MenuAction.SEARCH_SHOP_NAME: _menu_search_shop_name,
    MenuAction.SEARCH_ADDRESS: _menu_search_address,
    MenuAction.SHARE_LOCATION: _menu_share_location,
    MenuAction.FAVORITES: _menu_favorites,
    MenuAction.RECENT_SEARCH: _menu_recent_search,
    MenuAction.MORE_INFO: _menu_more_info,
}


def handle_menu(line_bot_api, reply_token, user, params):
    """處理 Rich Menu 選單動作（使用字典分派）"""
    menu_type = params.get('type')
    handler = MENU_HANDLERS.get(menu_type)

    if handler:
        handler(line_bot_api, reply_token, user)
    else:
        logger.warning(f'Unknown menu type: {menu_type}')


# Action Dispatch Table
ACTION_HANDLERS = {
    'favorite': handle_favorite,
    'unfavorite': handle_unfavorite,
    'view_detail': handle_view_detail,
    'recent_search': handle_recent_search,
    'menu': handle_menu,
}
