from django.urls import re_path

from cafe import views

# token 為 secrets.token_urlsafe(32)：43 字元 base64url；格式不符直接由路由回 404，不查資料庫
TOKEN = r'(?P<token>[A-Za-z0-9_-]{43})'

urlpatterns = [
    re_path(rf'^map/{TOKEN}/$', views.favorite_map_page, name='favorite_map_page'),
    re_path(rf'^map/{TOKEN}/data\.json$', views.favorite_map_data, name='favorite_map_data'),
]
