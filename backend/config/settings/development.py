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

# Fixed Fernet key for local dev/test (NOT secret, NOT used in production)
# Generate a real one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FERNET_KEY = 'ZmDfcTF7_60GrrY167zsiPd67oj5gFmr3D_K4nRr7X0='
