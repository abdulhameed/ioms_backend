from django.conf import settings
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('apps.core.urls')),
    # Phase 2+ app URLs registered here as each phase completes:
    # path('api/v1/', include('apps.users.urls')),
    # path('api/v1/', include('apps.approvals.urls')),
    # path('api/v1/', include('apps.projects.urls')),
    # path('api/v1/', include('apps.shortlets.urls')),
    # path('api/v1/', include('apps.maintenance.urls')),
    # path('api/v1/', include('apps.notifications.urls')),
]

if settings.DEBUG:
    try:
        import debug_toolbar
        urlpatterns += [path('__debug__/', include(debug_toolbar.urls))]
    except ImportError:
        pass
