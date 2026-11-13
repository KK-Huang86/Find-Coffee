from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_safe

from cafe.models import FavoriteMap
from cafe.services.favorite_map import get_map_snapshot

# 咖啡地圖頁面只需要自身 static、MapLibre CDN、OpenFreeMap 底圖與 https 店家照片
FAVORITE_MAP_CSP = '; '.join([
    "default-src 'self'",
    "script-src 'self' https://unpkg.com",
    "style-src 'self' https://unpkg.com",
    "img-src 'self' data: blob: https:",
    "connect-src 'self' https://tiles.openfreemap.org",
    "font-src 'self' https://tiles.openfreemap.org",
    "worker-src blob:",
    "child-src blob:",
    "base-uri 'none'",
    "form-action 'none'",
    "frame-ancestors 'none'",
])


def _with_map_headers(response):
    # token 在網址內：不讓搜尋引擎收錄，也不透過 Referer 外流到底圖服務
    response['X-Robots-Tag'] = 'noindex'
    response['Referrer-Policy'] = 'strict-origin'
    response['Content-Security-Policy'] = FAVORITE_MAP_CSP
    return response


@require_safe
def favorite_map_page(request, token):
    """地圖頁面殼：不含任何使用者或店家資料，資料由前端向 data.json 取得"""
    if not FavoriteMap.objects.filter(token=token).exists():
        raise Http404
    return _with_map_headers(render(request, 'cafe/favorite_map.html'))


@require_safe
def favorite_map_data(request, token):
    """地圖資料端點：回傳 token 對應的 snapshot"""
    snapshot = get_map_snapshot(token)
    if snapshot is None:
        raise Http404
    response = JsonResponse(snapshot, json_dumps_params={'ensure_ascii': False})
    response['Cache-Control'] = 'private, max-age=60'
    return _with_map_headers(response)
