from urllib.parse import urlparse

from django.conf import settings
from django.core.checks import Warning, register

LOCAL_HOSTS = {'localhost', '127.0.0.1', '0.0.0.0', '::1'}


@register()
def check_public_base_url(app_configs, **kwargs):
    """正式環境若仍用 localhost，使用者會收到打不開的咖啡地圖連結；尚無網域前以警告提醒，不阻擋啟動"""
    if getattr(settings, 'ENVIRONMENT', None) != 'production':
        return []
    host = (urlparse(settings.PUBLIC_BASE_URL or '').hostname or '').lower()
    if host and host not in LOCAL_HOSTS:
        return []
    return [Warning(
        f'PUBLIC_BASE_URL 為 {settings.PUBLIC_BASE_URL!r}，正式環境的咖啡地圖連結將無法在使用者手機開啟',
        hint='在 .env 設定 PUBLIC_BASE_URL 為對外網域，例如 https://coffee.example.com',
        id='cafe.W001',
    )]
