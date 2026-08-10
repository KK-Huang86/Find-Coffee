"""
驗證 line_bot.builders.flex_builder 對 5 個 Builder 類別的 re-export
與各自實際實作模組匯入的是同一個物件，確保既有呼叫端 import 路徑不需修改。
"""

from line_bot.builders.flex_builder import (
    FlexMessageBuilder,
    LineMessageBuilder,
    PostbackBuilder,
    FavoritesPageBuilder,
    QuickReplyBuilder,
)
from line_bot.builders.shop_flex_message import FlexMessageBuilder as NewFlexMessageBuilder
from line_bot.builders.message_sender import LineMessageBuilder as NewLineMessageBuilder
from line_bot.builders.postback import PostbackBuilder as NewPostbackBuilder
from line_bot.builders.favorites_page import FavoritesPageBuilder as NewFavoritesPageBuilder
from line_bot.builders.quick_reply import QuickReplyBuilder as NewQuickReplyBuilder


class TestFlexBuilderCompatReExports:
    """測試 flex_builder.py 相容層 re-export 與新模組實作為同一物件"""

    def test_flex_message_builder_is_same_object(self):
        assert FlexMessageBuilder is NewFlexMessageBuilder

    def test_line_message_builder_is_same_object(self):
        assert LineMessageBuilder is NewLineMessageBuilder

    def test_postback_builder_is_same_object(self):
        assert PostbackBuilder is NewPostbackBuilder

    def test_favorites_page_builder_is_same_object(self):
        assert FavoritesPageBuilder is NewFavoritesPageBuilder

    def test_quick_reply_builder_is_same_object(self):
        assert QuickReplyBuilder is NewQuickReplyBuilder
