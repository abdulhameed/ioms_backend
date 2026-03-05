"""Development settings — DEBUG=True, extra dev tools."""

from .base import *  # noqa: F401, F403

DEBUG = True

# Allow all hosts in local dev
ALLOWED_HOSTS = ['*']

# Django Debug Toolbar
INSTALLED_APPS += ['debug_toolbar', 'django_extensions']  # noqa: F405

MIDDLEWARE = [  # noqa: F405
    'debug_toolbar.middleware.DebugToolbarMiddleware',
] + MIDDLEWARE  # noqa: F405

INTERNAL_IPS = ['127.0.0.1']

# Silk profiling (accessible at /silk/)
SILKY_PYTHON_PROFILER = True

# Print emails to console instead of sending
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
