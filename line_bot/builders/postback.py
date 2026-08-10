from linebot.v3.messaging import TemplateMessage


class PostbackBuilder:

    @staticmethod
    def create_cafe_action_postback(info_d, is_favorited=False):
        """
        統一的postback 格式為 e.g. action=favorite&pid=XXXX
        action=動作&place_id=XXX
        """

        place_id = info_d['place_id']

        # TODO: data use urlencode(payload)

        favorite_action = {
            'type': 'postback',
            'label': '💔 取消收藏' if is_favorited else '⭐ 收藏',
            'data': f'action=unfavorite&place_id={place_id}' if is_favorited else f'action=favorite&place_id={place_id}'
        }

        buttons_template = {
            'type': 'template',
            'altText': '操作選單',
            'template': {
                'type': 'buttons',
                'text': '想對這間咖啡店做什麼？',
                'actions': [
                    favorite_action,
                    {
                        'type': 'postback',
                        'label': '🔗 分享',
                        'data': f'action=share&place_id={place_id}'
                    },
                    {
                        'type': 'postback',
                        'label': '⭐ 評價',
                        'data': f'action=vote&place_id={place_id}'
                    },
                    {
                        'type': 'postback',
                        'label': '🤖 看看AI怎麼說',
                        'data': f'action=ask_ai&place_id={place_id}'
                    }
                ]
            }
        }

        button_message = TemplateMessage.from_dict(buttons_template)

        return button_message
