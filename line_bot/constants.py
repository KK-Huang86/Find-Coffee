# Sentinel：代表 get_or_create_cafe_info 因額度不足而回傳，讓呼叫端顯示對應訊息
QUOTA_EXCEEDED = 'QUOTA_EXCEEDED'


class UserState:
    NORMAL = '初始'
    WAITING_SHOP_NAME = '等待查詢店名'
    WAITING_ADDRESS = '等待查詢路名'
    WAITING_VOTE = '等待評價'


# 投票屬性順序
VOTE_ATTRIBUTES = ['socket', 'limited_time', 'quiet', 'cheap']

# 投票屬性對應的問題文字
VOTE_QUESTIONS = {
    'socket': '這間店有插座嗎？🔌',
    'limited_time': '這間店會限時嗎？⏰',
    'quiet': '這間店安靜嗎？🤫',
    'cheap': '這間店價格如何？💰',
}

# 投票選項對應的值
VOTE_OPTIONS = {
    'socket': [
        ('yes', '有'),
        ('maybe', '部分座位'),
        ('no', '沒有'),
        ('unknown', '不確定'),
    ],
    'limited_time': [
        ('yes', '會限時'),
        ('maybe', '看情況'),
        ('no', '不限時'),
        ('unknown', '不確定'),
    ],
    'quiet': [
        ('yes', '安靜'),
        ('maybe', '普通'),
        ('no', '吵雜'),
        ('unknown', '不確定'),
    ],
    'cheap': [
        ('yes', '便宜'),
        ('maybe', '普通'),
        ('no', '偏貴'),
        ('unknown', '不確定'),
    ],
}


class MenuText:
    SHARE_LOCATION = '分享位置查詢'
    SEARCH_SHOP_NAME = '店名查詢'
    SEARCH_ADDRESS = '路名查詢'
    FAVORITES = '收藏的咖啡店'
    RECENT_SEARCH = '最近查詢'
    MORE_INFO = '更多資訊'


class MenuAction:
    SHARE_LOCATION = 'share_location'
    SEARCH_SHOP_NAME = 'search_shop_name'
    SEARCH_ADDRESS = 'search_address'
    FAVORITES = 'favorites'
    RECENT_SEARCH = 'recent_search'
    MORE_INFO = 'more_info'
