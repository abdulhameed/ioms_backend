"""
Shared pytest fixtures for the full test suite.
Phase-specific fixtures live in their own test files or conftest sections.
"""

import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    """Unauthenticated DRF API client."""
    return APIClient()


@pytest.fixture
def auth_client(api_client, django_user_model):
    """
    Returns a helper that authenticates the client as a given user.
    Usage: auth_client(user)
    """
    def _auth(user):
        api_client.force_authenticate(user=user)
        return api_client
    return _auth
