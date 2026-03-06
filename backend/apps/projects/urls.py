"""
Projects app URL patterns — Phase 4.
"""

from django.urls import path

from apps.projects.views import (
    DocumentListCreateView,
    MilestoneDetailView,
    MilestoneListCreateView,
    ProjectBudgetView,
    ProjectDashboardView,
    ProjectDetailView,
    ProjectListCreateView,
    ProjectSubmitView,
    RequisitionDetailView,
    RequisitionListCreateView,
    RequisitionSubmitView,
    SiteReportDetailView,
    SiteReportListCreateView,
    SiteReportPDFView,
)

urlpatterns = [
    # Dashboard must come before <uuid:pk> to avoid conflict
    path("projects/dashboard/", ProjectDashboardView.as_view(), name="project-dashboard"),

    path("projects/", ProjectListCreateView.as_view(), name="project-list"),
    path("projects/<uuid:pk>/", ProjectDetailView.as_view(), name="project-detail"),
    path("projects/<uuid:pk>/submit/", ProjectSubmitView.as_view(), name="project-submit"),
    path("projects/<uuid:pk>/budget/", ProjectBudgetView.as_view(), name="project-budget"),

    path("projects/<uuid:pk>/milestones/", MilestoneListCreateView.as_view(), name="milestone-list"),
    path("projects/<uuid:pk>/milestones/<uuid:mid>/", MilestoneDetailView.as_view(), name="milestone-detail"),

    path("projects/<uuid:pk>/documents/", DocumentListCreateView.as_view(), name="document-list"),

    path("projects/<uuid:pk>/site-reports/", SiteReportListCreateView.as_view(), name="site-report-list"),
    path("projects/<uuid:pk>/site-reports/<uuid:rid>/", SiteReportDetailView.as_view(), name="site-report-detail"),
    path("projects/<uuid:pk>/site-reports/<uuid:rid>/pdf/", SiteReportPDFView.as_view(), name="site-report-pdf"),

    path("projects/<uuid:pk>/requisitions/", RequisitionListCreateView.as_view(), name="requisition-list"),
    path("projects/<uuid:pk>/requisitions/<uuid:rid>/", RequisitionDetailView.as_view(), name="requisition-detail"),
    path("projects/<uuid:pk>/requisitions/<uuid:rid>/submit/", RequisitionSubmitView.as_view(), name="requisition-submit"),
]
