from django.core.management import get_commands


class TestRunserverStatic:
    """runserver 改由 WhiteNoise serve static，帶 Cache-Control，避免瀏覽器沿用舊版 JS"""

    def test_runserver_command_comes_from_whitenoise(self):
        assert get_commands()['runserver'] == 'whitenoise.runserver_nostatic'
