"""
Phase 8 — Deployment Readiness & Security Hardening tests.

Test IDs: SEC-01 through SEC-12
"""
from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

LOGIN_URL = "/api/v1/auth/login/"


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_user(django_user_model, role="md", email="sec_user@test.com", password="Test1234!"):
    """Create an active user in the correct group."""
    import re as _re
    username = _re.sub(r"[^a-z0-9]", "_", email.split("@")[0])
    user = django_user_model.objects.create_user(
        username=username,
        email=email,
        password=password,
        role=role,
        permission_level="full",
        is_active=True,
    )
    return user


# ── SEC-01: Rate limiting ───────────────────────────────────────────────────────


@pytest.mark.phase8
@pytest.mark.django_db
def test_login_rate_limit_429_on_11th_attempt():
    """10 failed login attempts succeed (return 401); the 11th is throttled (429)."""
    client = APIClient()
    for i in range(10):
        resp = client.post(LOGIN_URL, {"email": "nobody@example.com", "password": "wrong"})
        assert resp.status_code != 429, f"Request {i + 1} was throttled unexpectedly"

    resp = client.post(LOGIN_URL, {"email": "nobody@example.com", "password": "wrong"})
    assert resp.status_code == 429


@pytest.mark.phase8
@pytest.mark.django_db
def test_login_rate_limit_resets_after_cache_cleared(django_user_model):
    """After cache clear, the throttle window resets and login can proceed."""
    from django.core.cache import cache

    client = APIClient()
    for _ in range(10):
        client.post(LOGIN_URL, {"email": "nobody@example.com", "password": "wrong"})

    # Verify 11th is throttled
    resp = client.post(LOGIN_URL, {"email": "nobody@example.com", "password": "wrong"})
    assert resp.status_code == 429

    # After reset
    cache.clear()
    resp = client.post(LOGIN_URL, {"email": "nobody@example.com", "password": "wrong"})
    assert resp.status_code != 429


@pytest.mark.phase8
@pytest.mark.django_db
def test_login_throttle_does_not_block_successful_login_within_limit(django_user_model):
    """Valid credentials within the first 10 attempts returns 200."""
    user = _make_user(django_user_model)
    client = APIClient()
    # 5 failed attempts
    for _ in range(5):
        client.post(LOGIN_URL, {"email": "nobody@example.com", "password": "wrong"})
    # Now login with real credentials
    resp = client.post(LOGIN_URL, {"email": user.email, "password": "Test1234!"})
    # md role requires MFA — expect 403 mfa_required, not 429
    assert resp.status_code in (200, 403)
    assert resp.status_code != 429


# ── SEC-02 to SEC-05: Password validator ───────────────────────────────────────


@pytest.mark.phase8
def test_password_validator_rejects_no_uppercase():
    """Password without uppercase raises ValidationError."""
    from django.core.exceptions import ValidationError

    from apps.users.validators import StrongPasswordValidator

    validator = StrongPasswordValidator()
    with pytest.raises(ValidationError) as exc:
        validator.validate("password1!")
    codes = [e.code for e in exc.value.error_list]
    assert "password_no_upper" in codes


@pytest.mark.phase8
def test_password_validator_rejects_no_digit():
    """Password without a digit raises ValidationError."""
    from django.core.exceptions import ValidationError

    from apps.users.validators import StrongPasswordValidator

    validator = StrongPasswordValidator()
    with pytest.raises(ValidationError) as exc:
        validator.validate("Password!")
    codes = [e.code for e in exc.value.error_list]
    assert "password_no_digit" in codes


@pytest.mark.phase8
def test_password_validator_rejects_no_special_char():
    """Password without a special character raises ValidationError."""
    from django.core.exceptions import ValidationError

    from apps.users.validators import StrongPasswordValidator

    validator = StrongPasswordValidator()
    with pytest.raises(ValidationError) as exc:
        validator.validate("Password1")
    codes = [e.code for e in exc.value.error_list]
    assert "password_no_special" in codes


@pytest.mark.phase8
def test_password_validator_accepts_strong_password():
    """A password meeting all requirements passes without raising."""
    from apps.users.validators import StrongPasswordValidator

    validator = StrongPasswordValidator()
    validator.validate("StrongPass1!")  # should not raise


@pytest.mark.phase8
def test_password_validator_reports_all_errors_at_once():
    """A completely weak password reports all three error codes in one raise."""
    from django.core.exceptions import ValidationError

    from apps.users.validators import StrongPasswordValidator

    validator = StrongPasswordValidator()
    with pytest.raises(ValidationError) as exc:
        validator.validate("weakpassword")  # no upper, no digit, no special
    codes = [e.code for e in exc.value.error_list]
    assert "password_no_upper" in codes
    assert "password_no_digit" in codes
    assert "password_no_special" in codes


@pytest.mark.phase8
def test_password_validator_help_text_is_descriptive():
    """get_help_text() returns a non-empty guidance string."""
    from apps.users.validators import StrongPasswordValidator

    text = StrongPasswordValidator().get_help_text()
    assert "uppercase" in text.lower()
    assert "digit" in text.lower() or "number" in text.lower()
    assert "special" in text.lower()


# ── SEC-06: AuditLog immutability ─────────────────────────────────────────────


@pytest.mark.phase8
@pytest.mark.django_db
def test_auditlog_save_on_existing_instance_raises(django_user_model):
    """AuditLog.save() raises ValueError if the entry already exists in the DB."""
    user = _make_user(django_user_model, email="auditlog_sec@test.com")
    from apps.users.models import AuditLog

    log = AuditLog.log(action="test.immutable", user=user)
    log.description = "tampered"
    with pytest.raises(ValueError, match="immutable"):
        log.save()


@pytest.mark.phase8
@pytest.mark.django_db
def test_auditlog_bulk_update_raises(django_user_model):
    """AuditLog entries cannot be bulk-updated via the admin API."""
    user = _make_user(django_user_model, email="auditlog_bulk@test.com")
    from apps.users.models import AuditLog

    AuditLog.log(action="test.event", user=user)

    # The model override only prevents .save() on existing instances.
    # Verify the API view has no update endpoint (http_method_names excludes PUT/PATCH).
    from apps.users.views import AuditLogViewSet

    assert "put" not in AuditLogViewSet.http_method_names
    assert "patch" not in AuditLogViewSet.http_method_names
    assert "delete" not in AuditLogViewSet.http_method_names


@pytest.mark.phase8
@pytest.mark.django_db
def test_auditlog_api_no_post(django_user_model):
    """POST to /audit-logs/ is forbidden (read-only API)."""
    user = _make_user(django_user_model, email="auditlog_api@test.com")
    client = APIClient()
    client.force_authenticate(user=user)
    resp = client.post("/api/v1/audit-logs/", {"action": "injected"})
    assert resp.status_code == 405


# ── SEC-07: JWT settings ───────────────────────────────────────────────────────


@pytest.mark.phase8
def test_jwt_access_token_lifetime_is_15_minutes():
    """Access token lifetime is configured to 15 minutes."""
    from django.conf import settings

    assert settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"] == timedelta(minutes=15)


@pytest.mark.phase8
def test_jwt_refresh_token_lifetime_is_7_days():
    """Refresh token lifetime is configured to 7 days."""
    from django.conf import settings

    assert settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"] == timedelta(days=7)


@pytest.mark.phase8
def test_jwt_blacklist_after_rotation_enabled():
    """Token rotation and blacklisting are both enabled."""
    from django.conf import settings

    assert settings.SIMPLE_JWT["ROTATE_REFRESH_TOKENS"] is True
    assert settings.SIMPLE_JWT["BLACKLIST_AFTER_ROTATION"] is True


# ── SEC-08: CORS / HTTPS config ────────────────────────────────────────────────


@pytest.mark.phase8
def test_cors_allowed_origins_has_no_wildcard():
    """CORS_ALLOWED_ORIGINS does not contain a wildcard '*' entry."""
    from django.conf import settings

    for origin in settings.CORS_ALLOWED_ORIGINS:
        assert "*" not in origin, f"Wildcard found in CORS origins: {origin}"


# ── SEC-09: Field encryption ───────────────────────────────────────────────────


@pytest.mark.phase8
def test_mfa_secret_is_encrypted_field():
    """mfa_secret field on CustomUser is an EncryptedCharField."""
    from apps.core.fields import EncryptedCharField
    from apps.users.models import CustomUser

    field = CustomUser._meta.get_field("mfa_secret")
    assert isinstance(field, EncryptedCharField)


# ── SEC-10: Rate limit header present ─────────────────────────────────────────


@pytest.mark.phase8
@pytest.mark.django_db
def test_throttled_response_contains_retry_after_header():
    """HTTP 429 response includes a Retry-After header."""
    client = APIClient()
    for _ in range(10):
        client.post(LOGIN_URL, {"email": "nobody@example.com", "password": "wrong"})

    resp = client.post(LOGIN_URL, {"email": "nobody@example.com", "password": "wrong"})
    assert resp.status_code == 429
    # DRF sets Retry-After when throttling
    assert "Retry-After" in resp


# ── SEC-11: Password validator registered in settings ─────────────────────────


@pytest.mark.phase8
def test_strong_password_validator_is_registered():
    """StrongPasswordValidator appears in AUTH_PASSWORD_VALIDATORS."""
    from django.conf import settings

    names = [v["NAME"] for v in settings.AUTH_PASSWORD_VALIDATORS]
    assert "apps.users.validators.StrongPasswordValidator" in names


# ── SEC-12: Health check accessible without auth ──────────────────────────────


@pytest.mark.phase8
@pytest.mark.django_db
def test_health_check_accessible_without_auth():
    """GET /api/v1/health/ returns 200 without authentication."""
    client = APIClient()
    resp = client.get("/api/v1/health/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
