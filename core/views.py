from django.db import connection
from django.http import JsonResponse


# for livenessProbe
def liveness(request):
    return JsonResponse({'status': 'ok'})

# readinessProbe
def readiness(request):
    try:
        connection.ensure_connection()
    except Exception:
        return JsonResponse({'status': 'error', 'detail': 'db unavailable'}, status=503)
    return JsonResponse({'status': 'ok'})
