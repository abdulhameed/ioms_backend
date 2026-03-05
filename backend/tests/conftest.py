"""
Shared pytest fixtures for the full test suite.
Phase-specific fixtures live in their own test files or conftest sections.
"""

import pytest
from django.contrib.auth.models import Group
from rest_framework.test import APIClient


@pytest.fixture(autouse=True)
def clear_cache():
    """Flush the cache (including throttle counters) before every test."""
    from django.core.cache import cache
    cache.clear()
    yield


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


# ── User factories ──────────────────────────────────────────────────────────────

def _make_user(django_user_model, role, permission_level="full", **kwargs):
    """Helper that creates a user AND puts them in the correct group."""
    email = kwargs.pop("email", f"{role}_{permission_level}@example.com")
    username = kwargs.pop("username", email.split("@")[0])
    password = kwargs.pop("password", "Test1234!")
    user = django_user_model.objects.create_user(
        username=username,
        email=email,
        password=password,
        role=role,
        permission_level=permission_level,
        is_active=True,
        **kwargs,
    )
    # signal sync_user_group fires on save — group already added
    return user


@pytest.fixture
def md_user(django_user_model):
    return _make_user(django_user_model, "md", email="md@example.com")


@pytest.fixture
def hr_full_user(django_user_model):
    return _make_user(
        django_user_model, "hr", "full", email="hr_full@example.com", department="hr"
    )


@pytest.fixture
def hr_limited_user(django_user_model):
    return _make_user(
        django_user_model, "hr", "limited", email="hr_limited@example.com", department="hr"
    )


@pytest.fixture
def finance_full_user(django_user_model):
    return _make_user(
        django_user_model, "finance", "full", email="finance_full@example.com", department="finance"
    )


@pytest.fixture
def pm_full_user(django_user_model):
    return _make_user(
        django_user_model, "pm", "full", email="pm_full@example.com", department="pm"
    )


@pytest.fixture
def active_user(django_user_model):
    """Generic active user with no role (for simple auth tests)."""
    return django_user_model.objects.create_user(
        username="active_user",
        email="active@example.com",
        password="Test1234!",
        is_active=True,
    )
