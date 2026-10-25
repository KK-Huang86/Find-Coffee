from line_bot import event_handlers, views


class TestLineApiHost:
    """LINE Messaging API host 由 LINE_API_HOST 設定，預設為正式網址（壓測時指向 mock server）"""

    def test_event_handlers_default_host(self):
        assert event_handlers.configuration.host == 'https://api.line.me'

    def test_views_default_host(self):
        assert views.configuration.host == 'https://api.line.me'

    def test_event_handlers_and_views_share_same_host(self):
        assert event_handlers.LINE_API_HOST == views.LINE_API_HOST
