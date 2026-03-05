from django.urls import path

from . import views

urlpatterns = [
    path("", views.api_root, name="api-root"),  # GET /api/v1/
    path("health/", views.health_check, name="health-check"),  # GET /api/v1/health/
]
