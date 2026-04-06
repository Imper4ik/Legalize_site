from django.http import JsonResponse
from django.db import connection

def healthcheck(request):
    try:
        connection.ensure_connection()
        db_status = "ok"
    except Exception:
        db_status = "error"
    
    return JsonResponse(
        {"status": "ok", "database": db_status},
        status=200 if db_status == "ok" else 503
    )
