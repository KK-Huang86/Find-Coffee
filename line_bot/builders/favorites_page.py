from linebot.v3.messaging import FlexMessage, FlexBubble

from line_bot.builders.shop_flex_message import FlexMessageBuilder


class FavoritesPageBuilder:

    @staticmethod
    def build_page_message(favorites, page_num=1):
        """
        以列表 bubble 呈現一頁收藏（最多 15 筆）。
        每一列可點擊，觸發 view_detail postback。
        """
        title = '❤️ 我的收藏' if page_num == 1 else f'❤️ 我的收藏（第 {page_num} 頁）'

        contents = [
            {'type': 'text', 'text': title, 'weight': 'bold', 'size': 'xl', 'margin': 'md'},
            {'type': 'separator', 'margin': 'lg'},
        ]

        for i, fav in enumerate(favorites, 1):
            today_hours = FlexMessageBuilder.format_opening_hours(fav.cafe.opening_hours)
            shop_box = {
                'type': 'box',
                'layout': 'vertical',
                'margin': 'lg',
                'spacing': 'xs',
                'contents': [
                    {
                        'type': 'box',
                        'layout': 'baseline',
                        'spacing': 'sm',
                        'contents': [
                            {
                                'type': 'text',
                                'text': f'{i}.',
                                'size': 'sm',
                                'color': '#aaaaaa',
                                'flex': 0,
                            },
                            {
                                'type': 'text',
                                'text': fav.cafe.name,
                                'weight': 'bold',
                                'size': 'sm',
                                'wrap': True,
                                'flex': 1,
                            },
                        ]
                    },
                    {
                        'type': 'text',
                        'text': fav.cafe.address or '',
                        'size': 'xs',
                        'color': '#aaaaaa',
                        'wrap': True,
                    },
                    {
                        'type': 'text',
                        'text': f'⭐ {fav.cafe.rating if fav.cafe.rating is not None else "N/A"}',                        'size': 'xs',
                        'color': '#999999',
                    },
                    {
                        'type': 'text',
                        'text': f'今日營業時間: {today_hours}',
                        'size': 'xs',
                        'color': '#aaaaaa',
                        'wrap': True,
                    },
                ],
                'action': {
                    'type': 'postback',
                    'data': f'action=view_detail&place_id={fav.cafe.place_id}',
                }
            }
            contents.append(shop_box)
            if i < len(favorites):
                contents.append({'type': 'separator', 'margin': 'sm'})

        flex_dict = {
            'type': 'bubble',
            'body': {
                'type': 'box',
                'layout': 'vertical',
                'contents': contents,
            }
        }

        alt_text = '我的收藏清單' if page_num == 1 else f'我的收藏清單（第 {page_num} 頁）'
        return FlexMessage(
            alt_text=alt_text,
            contents=FlexBubble.from_dict(flex_dict),
        )
