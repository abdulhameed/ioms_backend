"""
Maintenance app URL patterns — Phase 6.
"""

from django.urls import path

from apps.maintenance.views import (
    MaintenanceAcceptView,
    MaintenanceAssignView,
    MaintenanceCloseView,
    MaintenanceDetailView,
    MaintenanceListCreateView,
    MaintenanceMetricsView,
    MaintenancePhotoView,
    MaintenanceUpdateStatusView,
)

urlpatterns = [
    # metrics must come before <uuid:pk> to avoid conflict
    path("maintenance/metrics/", MaintenanceMetricsView.as_view(), name="maintenance-metrics"),

    path("maintenance/", MaintenanceListCreateView.as_view(), name="maintenance-list"),
    path("maintenance/<uuid:pk>/", MaintenanceDetailView.as_view(), name="maintenance-detail"),
    path("maintenance/<uuid:pk>/assign/", MaintenanceAssignView.as_view(), name="maintenance-assign"),
    path("maintenance/<uuid:pk>/accept/", MaintenanceAcceptView.as_view(), name="maintenance-accept"),
    path(
        "maintenance/<uuid:pk>/update-status/",
        MaintenanceUpdateStatusView.as_view(),
        name="maintenance-update-status",
    ),
    path("maintenance/<uuid:pk>/close/", MaintenanceCloseView.as_view(), name="maintenance-close"),
    path("maintenance/<uuid:pk>/photos/", MaintenancePhotoView.as_view(), name="maintenance-photos"),
]
