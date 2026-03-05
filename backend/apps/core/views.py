from django.db import connection, OperationalError
from django.core.cache import cache
from django.http import JsonResponse


def api_root(request):
    """GET /api/v1/ — API info response for Phase 1 health check."""
    return JsonResponse(
        {
            "api": "IOMS Backend API",
            "version": "v1",
            "status": "operational",
            "docs": "/api/v1/schema/",
        }
    )


def health_check(request):
    """GET /api/v1/health/ — liveness probe for load balancers and monitoring."""
    db_status = "ok"
    try:
        connection.ensure_connection()
    except OperationalError:
        db_status = "error"

    redis_status = "ok"
    try:
        cache.set("_health", "1", timeout=5)
        if cache.get("_health") != "1":
            redis_status = "error"
    except Exception:
        redis_status = "error"

    overall = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"
    return JsonResponse(
        {"status": overall, "db": db_status, "redis": redis_status},
        status=200 if overall == "ok" else 503,
    )
