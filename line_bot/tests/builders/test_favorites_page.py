import pytest

from line_bot.builders.favorites_page import FavoritesPageBuilder
from cafe.tests.factories import CafeFactory, FavoriteFactory


@pytest.mark.django_db
class TestFavoritesPageBuilderBuildPageMessage:
    """測試 FavoritesPageBuilder.build_page_message"""

    def _body_contents(self, result):
        return result.to_dict()['contents']['body']['contents']

    def test_page_one_title_has_no_page_suffix(self):
        """第 1 頁標題不含頁碼"""
        fav = FavoriteFactory()
        result = FavoritesPageBuilder.build_page_message([fav], page_num=1)
        title_element = self._body_contents(result)[0]
        assert title_element['text'] == '❤️ 我的收藏'

    def test_page_two_title_has_page_suffix(self):
        """第 2 頁以上標題含頁碼"""
        fav = FavoriteFactory()
        result = FavoritesPageBuilder.build_page_message([fav], page_num=2)
        title_element = self._body_contents(result)[0]
        assert title_element['text'] == '❤️ 我的收藏（第 2 頁）'

    def test_alt_text_matches_page(self):
        """alt_text 隨頁碼變化"""
        fav = FavoriteFactory()
        result1 = FavoritesPageBuilder.build_page_message([fav], page_num=1)
        result2 = FavoritesPageBuilder.build_page_message([fav], page_num=2)
        assert result1.to_dict()['altText'] == '我的收藏清單'
        assert result2.to_dict()['altText'] == '我的收藏清單（第 2 頁）'

    def test_empty_favorites_has_only_title_and_separator(self):
        """0 筆收藏時，body 只有標題與分隔線，無店家列"""
        result = FavoritesPageBuilder.build_page_message([], page_num=1)
        contents = self._body_contents(result)
        assert len(contents) == 2
        assert contents[0]['type'] == 'text'
        assert contents[1]['type'] == 'separator'

    def test_single_favorite_has_no_trailing_separator(self):
        """1 筆收藏時，該列之後不再多加分隔線"""
        fav = FavoriteFactory()
        result = FavoritesPageBuilder.build_page_message([fav], page_num=1)
        contents = self._body_contents(result)
        # title, separator, shop_box
        assert len(contents) == 3
        assert contents[2]['action']['data'] == f'action=view_detail&place_id={fav.cafe.place_id}'

    def test_multiple_favorites_have_separators_between_rows(self):
        """多筆收藏時，每列之間皆有分隔線"""
        favs = [FavoriteFactory() for _ in range(3)]
        result = FavoritesPageBuilder.build_page_message(favs, page_num=1)
        contents = self._body_contents(result)
        # title, separator, box1, separator, box2, separator, box3
        assert len(contents) == 2 + 3 + 2
        separator_count = sum(1 for c in contents if c['type'] == 'separator')
        assert separator_count == 3

    def test_shop_box_contains_index_and_name(self):
        """店家列包含正確的序號與店名"""
        fav = FavoriteFactory(cafe=CafeFactory(name='測試咖啡店'))
        result = FavoritesPageBuilder.build_page_message([fav], page_num=1)
        shop_box = self._body_contents(result)[2]
        index_and_name_box = shop_box['contents'][0]
        index_text, name_text = index_and_name_box['contents']
        assert index_text['text'] == '1.'
        assert name_text['text'] == '測試咖啡店'

    def test_address_empty_string_when_blank(self):
        """cafe.address 為空字串時，地址列顯示空字串而不出錯"""
        fav = FavoriteFactory(cafe=CafeFactory(address=''))
        result = FavoritesPageBuilder.build_page_message([fav], page_num=1)
        shop_box = self._body_contents(result)[2]
        address_text = shop_box['contents'][1]
        assert address_text['text'] == ''

    def test_rating_none_shows_na(self):
        """cafe.rating 為 None 時，評分列顯示 N/A"""
        fav = FavoriteFactory(cafe=CafeFactory(rating=None))
        result = FavoritesPageBuilder.build_page_message([fav], page_num=1)
        shop_box = self._body_contents(result)[2]
        rating_text = shop_box['contents'][2]
        assert rating_text['text'] == '⭐ N/A'

    def test_handles_full_page_size_without_error(self):
        """對應 FAVORITES_PAGE_SIZE=15 的單頁上限，函式須能正常處理不出錯"""
        favs = [FavoriteFactory() for _ in range(15)]
        result = FavoritesPageBuilder.build_page_message(favs, page_num=1)
        contents = self._body_contents(result)
        shop_boxes = [c for c in contents if 'action' in c]
        assert len(shop_boxes) == 15
