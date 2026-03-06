"""
Approvals app URL patterns — Phase 3.
"""

from rest_framework.routers import DefaultRouter

from apps.approvals.views import ApprovalViewSet

router = DefaultRouter()
router.register(r"approvals", ApprovalViewSet, basename="approval")

urlpatterns = router.urls
