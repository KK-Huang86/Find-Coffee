import logging

from django.db import connection
from django.http import JsonResponse

logger = logging.getLogger(__name__)


# for livenessProbe
def liveness(request):
    return JsonResponse({'status': 'ok'})


# readinessProbe
def readiness(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except Exception:
        logger.exception('Readiness check failed: Database is unavailable.') # 動記錄目前 exception 與完整 traceback
        return JsonResponse({'status': 'error', 'detail': 'db unavailable'}, status=503)
    return JsonResponse({'status': 'ok'})
