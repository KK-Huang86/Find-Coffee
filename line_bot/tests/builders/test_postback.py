from line_bot.builders.postback import PostbackBuilder


class TestPostbackBuilderCreateCafeActionPostback:
    """測試 PostbackBuilder.create_cafe_action_postback"""

    def _make_info(self, place_id='test_place_id'):
        return {'place_id': place_id}

    def test_not_favorited_shows_star_label(self):
        """未收藏時，收藏按鈕顯示 '⭐ 收藏'"""
        result = PostbackBuilder.create_cafe_action_postback(self._make_info(), is_favorited=False)
        actions = result.to_dict()['template']['actions']
        fav_action = actions[0]
        assert fav_action['label'] == '⭐ 收藏'
        assert 'action=favorite' in fav_action['data']

    def test_favorited_shows_remove_label(self):
        """已收藏時，收藏按鈕顯示 '💔 取消收藏'"""
        result = PostbackBuilder.create_cafe_action_postback(self._make_info(), is_favorited=True)
        actions = result.to_dict()['template']['actions']
        fav_action = actions[0]
        assert fav_action['label'] == '💔 取消收藏'
        assert 'action=unfavorite' in fav_action['data']

    def test_postback_data_contains_place_id(self):
        """postback data 包含正確的 place_id"""
        result = PostbackBuilder.create_cafe_action_postback({'place_id': 'abc_xyz'})
        actions = result.to_dict()['template']['actions']
        for action in actions:
            assert 'place_id=abc_xyz' in action['data']

    def test_contains_four_actions(self):
        """按鈕選單包含 4 個 action（收藏、分享、評價、問 AI）"""
        result = PostbackBuilder.create_cafe_action_postback(self._make_info())
        actions = result.to_dict()['template']['actions']
        assert len(actions) == 4

    def test_all_action_labels_present(self):
        """按鈕選單包含所有預期的標籤"""
        result = PostbackBuilder.create_cafe_action_postback(self._make_info())
        labels = [a['label'] for a in result.to_dict()['template']['actions']]
        assert '⭐ 收藏' in labels
        assert '🔗 分享' in labels
        assert '⭐ 評價' in labels
        assert '🤖 看看AI怎麼說' in labels
