"""
Phase 2 — Authentication, RBAC & Audit tests.
AUTH-01 through AUTH-15.
"""

from unittest.mock import patch

import pyotp
import pytest
from django.contrib.auth.models import Group
from django.utils import timezone

from apps.users.models import AuditLog, CustomUser, EmailVerificationToken, Notification, PermissionGrant


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_limited_hr(django_user_model):
    return django_user_model.objects.create_user(
        username="hr_lim_target",
        email="hr_lim_target@example.com",
        password="Test1234!",
        role="hr",
        permission_level="limited",
        department="hr",
        is_active=True,
    )


# ── AUTH-01 ────────────────────────────────────────────────────────────────────

@pytest.mark.phase2
@pytest.mark.django_db
def test_auth01_register_creates_user_and_queues_email(api_client, hr_full_user):
    """HR creates user → HTTP 201; verification token in DB; email task queued."""
    api_client.force_authenticate(user=hr_full_user)

    with patch("apps.users.views.send_verification_email") as mock_task:
        resp = api_client.post(
            "/api/v1/auth/register/",
            {
                "email": "newstaff@example.com",
                "full_name": "New Staff",
                "role": "pm",
                "permission_level": "limited",
            },
            format="json",
        )

    assert resp.status_code == 201, resp.data
    user = CustomUser.objects.get(email="newstaff@example.com")
    assert not user.is_active
    assert EmailVerificationToken.objects.filter(user=user).exists()
    mock_task.delay.assert_called_once()


# ── AUTH-02 ────────────────────────────────────────────────────────────────────

@pytest.mark.phase2
@pytest.mark.django_db
def test_auth02_verify_email_activates_user(api_client, django_user_model):
    """Verify email with valid token → user.is_active=True."""
    user = django_user_model.objects.create_user(
        username="verifytest",
        email="verify@example.com",
        password=None,
        is_active=False,
    )
    token_obj = EmailVerificationToken.create_for_user(user)

    resp = api_client.post(
        "/api/v1/auth/verify-email/",
        {"token": token_obj.token},
        format="json",
    )

    assert resp.status_code == 200, resp.data
    user.refresh_from_db()
    assert user.is_active
    token_obj.refresh_from_db()
    assert token_obj.used_at is not None


# ── AUTH-03 ────────────────────────────────────────────────────────────────────

@pytest.mark.phase2
@pytest.mark.django_db
def test_auth03_expired_token_rejected(api_client, django_user_model):
    """Verify email with expired token → HTTP 400."""
    user = django_user_model.objects.create_user(
        username="expiredtest",
        email="expired@example.com",
        password=None,
        is_active=False,
    )
    token_obj = EmailVerificationToken.create_for_user(user)
    token_obj.expires_at = timezone.now() - timezone.timedelta(hours=1)
    token_obj.save()

    resp = api_client.post(
        "/api/v1/auth/verify-email/",
        {"token": token_obj.token},
        format="json",
    )

    assert resp.status_code == 400


# ── AUTH-04 ────────────────────────────────────────────────────────────────────

@pytest.mark.phase2
@pytest.mark.django_db
def test_auth04_login_returns_jwt_pair(api_client, active_user):
    """Login with correct credentials → HTTP 200; access + refresh present."""
    resp = api_client.post(
        "/api/v1/auth/login/",
        {"email": "active@example.com", "password": "Test1234!"},
        format="json",
    )

    assert resp.status_code == 200, resp.data
    assert "access" in resp.data
    assert "refresh" in resp.data


# ── AUTH-05 ────────────────────────────────────────────────────────────────────

@pytest.mark.phase2
@pytest.mark.django_db
def test_auth05_five_failures_lock_account(api_client, active_user):
    """5 wrong-password attempts → 401; 6th attempt → 423 account locked."""
    url = "/api/v1/auth/login/"
    payload = {"email": "active@example.com", "password": "WrongPass!"}

    with patch("apps.users.tasks.send_account_unlock_email"):
        for i in range(5):
            resp = api_client.post(url, payload, format="json")
            assert resp.status_code == 401, f"attempt {i + 1} should be 401"

        resp = api_client.post(url, payload, format="json")

    assert resp.status_code == 423


# ── AUTH-06 ────────────────────────────────────────────────────────────────────

@pytest.mark.phase2
@pytest.mark.django_db
def test_auth06_protected_endpoint_rejects_unauthenticated(api_client):
    """Access protected endpoint without token → 401."""
    resp = api_client.get("/api/v1/users/me/")
    assert resp.status_code == 401


# ── AUTH-07 ────────────────────────────────────────────────────────────────────

@pytest.mark.phase2
@pytest.mark.django_db
def test_auth07_hr_limited_cannot_create_user(api_client, hr_limited_user):
    """hr_limited tries to register a user → 403."""
    api_client.force_authenticate(user=hr_limited_user)
    resp = api_client.post(
        "/api/v1/auth/register/",
        {"email": "blocked@example.com", "role": "pm", "permission_level": "limited"},
        format="json",
    )
    assert resp.status_code == 403


# ── AUTH-08 ────────────────────────────────────────────────────────────────────

@pytest.mark.phase2
@pytest.mark.django_db
def test_auth08_role_change_updates_group(api_client, hr_full_user, django_user_model):
    """Role changed → user added to new group, removed from old group."""
    target = _make_limited_hr(django_user_model)
    assert target.groups.filter(name="hr_limited").exists()

    api_client.force_authenticate(user=hr_full_user)
    resp = api_client.put(
        f"/api/v1/users/{target.id}/",
        {"role": "hr", "permission_level": "full", "department": "hr"},
        format="json",
    )

    assert resp.status_code == 200, resp.data
    target.refresh_from_db()
    assert target.groups.filter(name="hr_full").exists()
    assert not target.groups.filter(name="hr_limited").exists()


# ── AUTH-09 ────────────────────────────────────────────────────────────────────

@pytest.mark.phase2
@pytest.mark.django_db
def test_auth09_promotion_to_full_deactivates_grants(api_client, hr_full_user, django_user_model):
    """Promotion to full permission_level → individual PermissionGrants deactivated."""
    from django.contrib.auth.models import Permission

    target = django_user_model.objects.create_user(
        username="promo_target",
        email="promo_target@example.com",
        password="Test1234!",
        role="hr",
        permission_level="limited",
        department="hr",
        is_active=True,
    )
    perm = Permission.objects.filter(codename__startswith="view_").first()
    grant = PermissionGrant.objects.create(
        user=target, permission=perm, granted_by=hr_full_user, is_active=True
    )

    api_client.force_authenticate(user=hr_full_user)
    api_client.put(
        f"/api/v1/users/{target.id}/",
        {"role": "hr", "permission_level": "full", "department": "hr"},
        format="json",
    )

    grant.refresh_from_db()
    assert not grant.is_active


# ── AUTH-10 ────────────────────────────────────────────────────────────────────

@pytest.mark.phase2
@pytest.mark.django_db
def test_auth10_manager_grants_permission_same_dept(api_client, hr_full_user, hr_limited_user):
    """Manager grants permission to same-dept subordinate → PermissionGrant active."""
    from django.contrib.auth.models import Permission

    perm = Permission.objects.filter(codename="view_customuser").first()

    api_client.force_authenticate(user=hr_full_user)
    resp = api_client.post(
        f"/api/v1/users/{hr_limited_user.id}/grant-permission/",
        {"permission_codename": "view_customuser"},
        format="json",
    )

    assert resp.status_code == 200, resp.data
    assert PermissionGrant.objects.filter(
        user=hr_limited_user, permission=perm, is_active=True
    ).exists()


# ── AUTH-11 ────────────────────────────────────────────────────────────────────

@pytest.mark.phase2
@pytest.mark.django_db
def test_auth11_cross_dept_grant_blocked(api_client, hr_full_user, finance_full_user):
    """Manager tries to grant permission to different-dept user → 403."""
    api_client.force_authenticate(user=hr_full_user)
    resp = api_client.post(
        f"/api/v1/users/{finance_full_user.id}/grant-permission/",
        {"permission_codename": "view_customuser"},
        format="json",
    )
    assert resp.status_code == 403


# ── AUTH-12 ────────────────────────────────────────────────────────────────────

@pytest.mark.phase2
@pytest.mark.django_db
def test_auth12_auditlog_created_for_key_events(api_client, hr_full_user, django_user_model):
    """AuditLog entry created on login, user_create, role_change."""
    initial_count = AuditLog.objects.count()

    # Event 1: login (creates an active user to log in as)
    login_user = django_user_model.objects.create_user(
        username="auditlogin",
        email="auditlogin@example.com",
        password="Test1234!",
        is_active=True,
    )
    api_client.post(
        "/api/v1/auth/login/",
        {"email": "auditlogin@example.com", "password": "Test1234!"},
        format="json",
    )

    # Event 2: user_create
    api_client.force_authenticate(user=hr_full_user)
    with patch("apps.users.views.send_verification_email"):
        api_client.post(
            "/api/v1/auth/register/",
            {"email": "auditcreate@example.com", "role": "pm", "permission_level": "limited"},
            format="json",
        )

    # Event 3: role_change
    created = CustomUser.objects.get(email="auditcreate@example.com")
    created.is_active = True
    created.save()
    api_client.put(
        f"/api/v1/users/{created.id}/",
        {"role": "finance", "permission_level": "limited"},
        format="json",
    )

    new_logs = AuditLog.objects.count() - initial_count
    assert new_logs >= 3


# ── AUTH-13 ────────────────────────────────────────────────────────────────────

@pytest.mark.phase2
@pytest.mark.django_db
def test_auth13_hr_limited_cannot_view_audit_log(api_client, hr_limited_user):
    """GET /audit-logs/ by hr_limited → 403."""
    api_client.force_authenticate(user=hr_limited_user)
    resp = api_client.get("/api/v1/audit-logs/")
    assert resp.status_code == 403


# ── AUTH-14 ────────────────────────────────────────────────────────────────────

@pytest.mark.phase2
@pytest.mark.django_db
def test_auth14_mfa_setup_and_verify(api_client, active_user):
    """MFA setup → TOTP code validates → full JWT issued."""
    api_client.force_authenticate(user=active_user)

    resp = api_client.post("/api/v1/auth/mfa/setup/", format="json")
    assert resp.status_code == 200
    secret = resp.data["secret"]

    totp = pyotp.TOTP(secret)
    code = totp.now()
    resp2 = api_client.post("/api/v1/auth/mfa/verify/", {"code": code}, format="json")

    assert resp2.status_code == 200, resp2.data
    assert "access" in resp2.data
    assert "refresh" in resp2.data

    active_user.refresh_from_db()
    assert active_user.mfa_enabled


# ── AUTH-15 ────────────────────────────────────────────────────────────────────

@pytest.mark.phase2
@pytest.mark.django_db
def test_auth15_logout_blacklists_token(api_client, active_user):
    """Logout → refresh token blacklisted → token/refresh returns 401."""
    resp = api_client.post(
        "/api/v1/auth/login/",
        {"email": "active@example.com", "password": "Test1234!"},
        format="json",
    )
    assert resp.status_code == 200
    refresh = resp.data["refresh"]

    api_client.force_authenticate(user=active_user)
    resp2 = api_client.post("/api/v1/auth/logout/", {"refresh": refresh}, format="json")
    assert resp2.status_code == 204

    api_client.force_authenticate(user=None)
    resp3 = api_client.post(
        "/api/v1/auth/token/refresh/",
        {"refresh": refresh},
        format="json",
    )
    assert resp3.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# Edge-case tests beyond the PRD AUTH-XX matrix
# ══════════════════════════════════════════════════════════════════════════════

# ── Registration edge cases ───────────────────────────────────────────────────

@pytest.mark.phase2
@pytest.mark.django_db
def test_register_duplicate_email_returns_400(api_client, hr_full_user, active_user):
    """Registering the same email twice → 400 with a clear error."""
    api_client.force_authenticate(user=hr_full_user)
    with patch("apps.users.views.send_verification_email"):
        resp = api_client.post(
            "/api/v1/auth/register/",
            {"email": "active@example.com"},  # active_user already has this email
            format="json",
        )
    assert resp.status_code == 400
    assert "email" in str(resp.data).lower()


@pytest.mark.phase2
@pytest.mark.django_db
def test_register_duplicate_phone_returns_400(api_client, hr_full_user, django_user_model):
    """Registering with a phone number already in use → 400."""
    django_user_model.objects.create_user(
        username="phoneuser", email="phoneuser@example.com",
        password="Test1234!", phone="08001234567", is_active=True,
    )
    api_client.force_authenticate(user=hr_full_user)
    with patch("apps.users.views.send_verification_email"):
        resp = api_client.post(
            "/api/v1/auth/register/",
            {"email": "newphone@example.com", "phone": "08001234567"},
            format="json",
        )
    assert resp.status_code == 400


@pytest.mark.phase2
@pytest.mark.django_db
def test_set_password_activates_user_and_enables_login(api_client, django_user_model):
    """set-password with valid token → password stored; user can log in."""
    user = django_user_model.objects.create_user(
        username="setpwtest", email="setpw@example.com",
        password=None, is_active=False,
    )
    token_obj = EmailVerificationToken.create_for_user(user)

    resp = api_client.post(
        "/api/v1/auth/set-password/",
        {"token": token_obj.token, "password": "NewPass99!"},
        format="json",
    )
    assert resp.status_code == 200

    user.refresh_from_db()
    assert user.is_active

    # User can now log in
    login_resp = api_client.post(
        "/api/v1/auth/login/",
        {"email": "setpw@example.com", "password": "NewPass99!"},
        format="json",
    )
    assert login_resp.status_code == 200


@pytest.mark.phase2
@pytest.mark.django_db
def test_set_password_with_used_token_returns_400(api_client, django_user_model):
    """set-password replay: token already consumed → 400."""
    user = django_user_model.objects.create_user(
        username="setpwreplay", email="setpwreplay@example.com",
        password=None, is_active=False,
    )
    token_obj = EmailVerificationToken.create_for_user(user)
    token_obj.consume()

    resp = api_client.post(
        "/api/v1/auth/set-password/",
        {"token": token_obj.token, "password": "NewPass99!"},
        format="json",
    )
    assert resp.status_code == 400


# ── Token edge cases ──────────────────────────────────────────────────────────

@pytest.mark.phase2
@pytest.mark.django_db
def test_verify_email_already_used_token_returns_400(api_client, django_user_model):
    """Replaying a consumed verification token → 400."""
    user = django_user_model.objects.create_user(
        username="replaytest", email="replay@example.com",
        password=None, is_active=False,
    )
    token_obj = EmailVerificationToken.create_for_user(user)
    # First use
    api_client.post("/api/v1/auth/verify-email/", {"token": token_obj.token}, format="json")

    # Second use (replay)
    resp = api_client.post("/api/v1/auth/verify-email/", {"token": token_obj.token}, format="json")
    assert resp.status_code == 400


@pytest.mark.phase2
@pytest.mark.django_db
def test_verify_email_nonexistent_token_returns_400(api_client):
    """Garbage token string → 400."""
    resp = api_client.post(
        "/api/v1/auth/verify-email/",
        {"token": "this-token-does-not-exist-at-all"},
        format="json",
    )
    assert resp.status_code == 400


# ── Login edge cases ──────────────────────────────────────────────────────────

@pytest.mark.phase2
@pytest.mark.django_db
def test_login_nonexistent_email_returns_401(api_client):
    """Email not in DB → 401 (not 404, to avoid account enumeration)."""
    resp = api_client.post(
        "/api/v1/auth/login/",
        {"email": "nobody@example.com", "password": "Test1234!"},
        format="json",
    )
    assert resp.status_code == 401


@pytest.mark.phase2
@pytest.mark.django_db
def test_login_inactive_user_returns_400(api_client, django_user_model):
    """Inactive (unverified) user → 400; failed_login_count NOT incremented."""
    user = django_user_model.objects.create_user(
        username="inactivelogin", email="inactive_login@example.com",
        password="Test1234!", is_active=False,
    )
    resp = api_client.post(
        "/api/v1/auth/login/",
        {"email": "inactive_login@example.com", "password": "Test1234!"},
        format="json",
    )
    assert resp.status_code == 400
    user.refresh_from_db()
    assert user.failed_login_count == 0  # counter must NOT increment


@pytest.mark.phase2
@pytest.mark.django_db
def test_login_correct_password_while_locked_still_423(api_client, active_user):
    """Even with the correct password, a locked account returns 423."""
    from django.utils import timezone as tz
    active_user.locked_until = tz.now() + tz.timedelta(minutes=10)
    active_user.save(update_fields=["locked_until"])

    resp = api_client.post(
        "/api/v1/auth/login/",
        {"email": "active@example.com", "password": "Test1234!"},
        format="json",
    )
    assert resp.status_code == 423


@pytest.mark.phase2
@pytest.mark.django_db
def test_login_auto_unlock_after_lockout_expires(api_client, active_user):
    """Account auto-unlocks once locked_until passes."""
    from freezegun import freeze_time
    from django.utils import timezone as tz

    # Lock the account
    with patch("apps.users.tasks.send_account_unlock_email"):
        for _ in range(5):
            api_client.post(
                "/api/v1/auth/login/",
                {"email": "active@example.com", "password": "WrongPass!"},
                format="json",
            )

    # 6th attempt → still locked
    resp = api_client.post(
        "/api/v1/auth/login/",
        {"email": "active@example.com", "password": "WrongPass!"},
        format="json",
    )
    assert resp.status_code == 423

    # 31 minutes later → lockout expired, correct password succeeds
    with freeze_time(tz.now() + tz.timedelta(minutes=31)):
        resp2 = api_client.post(
            "/api/v1/auth/login/",
            {"email": "active@example.com", "password": "Test1234!"},
            format="json",
        )
    assert resp2.status_code == 200


@pytest.mark.phase2
@pytest.mark.django_db
def test_successful_login_resets_failed_count(api_client, active_user):
    """3 failed attempts → successful login → counter back to 0."""
    for _ in range(3):
        api_client.post(
            "/api/v1/auth/login/",
            {"email": "active@example.com", "password": "WrongPass!"},
            format="json",
        )
    active_user.refresh_from_db()
    assert active_user.failed_login_count == 3

    api_client.post(
        "/api/v1/auth/login/",
        {"email": "active@example.com", "password": "Test1234!"},
        format="json",
    )
    active_user.refresh_from_db()
    assert active_user.failed_login_count == 0


# ── MFA edge cases ────────────────────────────────────────────────────────────

@pytest.mark.phase2
@pytest.mark.django_db
def test_mfa_verify_wrong_code_returns_400(api_client, active_user):
    """Wrong TOTP code → 400."""
    api_client.force_authenticate(user=active_user)
    api_client.post("/api/v1/auth/mfa/setup/", format="json")
    resp = api_client.post("/api/v1/auth/mfa/verify/", {"code": "000000"}, format="json")
    assert resp.status_code == 400


@pytest.mark.phase2
@pytest.mark.django_db
def test_mfa_verify_without_setup_returns_400(api_client, active_user):
    """Calling /mfa/verify/ before /mfa/setup/ (no secret stored) → 400."""
    api_client.force_authenticate(user=active_user)
    resp = api_client.post("/api/v1/auth/mfa/verify/", {"code": "123456"}, format="json")
    assert resp.status_code == 400


@pytest.mark.phase2
@pytest.mark.django_db
def test_login_blocks_md_without_mfa(api_client, django_user_model):
    """md role user with mfa_enabled=False → 403 on login."""
    user = django_user_model.objects.create_user(
        username="md_nomfa", email="md_nomfa@example.com",
        password="Test1234!", role="md", is_active=True,
    )
    assert not user.mfa_enabled

    resp = api_client.post(
        "/api/v1/auth/login/",
        {"email": "md_nomfa@example.com", "password": "Test1234!"},
        format="json",
    )
    assert resp.status_code == 403
    assert "mfa" in resp.data.get("error", "").lower()


# ── JWT / token management edge cases ────────────────────────────────────────

@pytest.mark.phase2
@pytest.mark.django_db
def test_token_refresh_works(api_client, active_user):
    """Valid refresh token → new access token returned."""
    resp = api_client.post(
        "/api/v1/auth/login/",
        {"email": "active@example.com", "password": "Test1234!"},
        format="json",
    )
    refresh = resp.data["refresh"]

    resp2 = api_client.post(
        "/api/v1/auth/token/refresh/",
        {"refresh": refresh},
        format="json",
    )
    assert resp2.status_code == 200
    assert "access" in resp2.data


@pytest.mark.phase2
@pytest.mark.django_db
def test_logout_without_refresh_token_returns_400(api_client, active_user):
    """POST /logout/ with empty body → 400."""
    api_client.force_authenticate(user=active_user)
    resp = api_client.post("/api/v1/auth/logout/", {}, format="json")
    assert resp.status_code == 400


@pytest.mark.phase2
@pytest.mark.django_db
def test_logout_with_invalid_token_returns_400(api_client, active_user):
    """POST /logout/ with garbage token → 400."""
    api_client.force_authenticate(user=active_user)
    resp = api_client.post(
        "/api/v1/auth/logout/",
        {"refresh": "not.a.valid.jwt.token"},
        format="json",
    )
    assert resp.status_code == 400


# ── User API edge cases ───────────────────────────────────────────────────────

@pytest.mark.phase2
@pytest.mark.django_db
def test_me_endpoint_returns_current_user(api_client, hr_full_user):
    """GET /users/me/ returns the authenticated user's profile."""
    api_client.force_authenticate(user=hr_full_user)
    resp = api_client.get("/api/v1/users/me/")
    assert resp.status_code == 200
    assert resp.data["email"] == hr_full_user.email
    assert resp.data["role"] == hr_full_user.role


@pytest.mark.phase2
@pytest.mark.django_db
def test_me_put_non_manager_cannot_change_role(api_client, hr_limited_user):
    """Non-manager updating own profile cannot change role."""
    api_client.force_authenticate(user=hr_limited_user)
    resp = api_client.put(
        "/api/v1/users/me/",
        {"full_name": "Updated Name", "role": "md", "permission_level": "full"},
        format="json",
    )
    assert resp.status_code == 200
    hr_limited_user.refresh_from_db()
    # Name should update; role must remain unchanged
    assert hr_limited_user.full_name == "Updated Name"
    assert hr_limited_user.role == "hr"
    assert hr_limited_user.permission_level == "limited"


@pytest.mark.phase2
@pytest.mark.django_db
def test_user_list_filter_by_role(api_client, hr_full_user, pm_full_user):
    """GET /users/?role=pm returns only PM users."""
    api_client.force_authenticate(user=hr_full_user)
    resp = api_client.get("/api/v1/users/?role=pm")
    assert resp.status_code == 200
    emails = [u["email"] for u in resp.data["results"]]
    assert pm_full_user.email in emails
    assert hr_full_user.email not in emails


@pytest.mark.phase2
@pytest.mark.django_db
def test_permissions_endpoint_returns_group_and_individual(api_client, hr_full_user, hr_limited_user):
    """GET /users/{id}/permissions/ lists group perms + individual grants."""
    api_client.force_authenticate(user=hr_full_user)
    resp = api_client.get(f"/api/v1/users/{hr_limited_user.id}/permissions/")
    assert resp.status_code == 200
    assert "group_permissions" in resp.data
    assert "individual_grants" in resp.data
    assert isinstance(resp.data["group_permissions"], list)


# ── Permission revoke & re-grant edge cases ───────────────────────────────────

@pytest.mark.phase2
@pytest.mark.django_db
def test_revoke_permission_deactivates_grant(api_client, hr_full_user, hr_limited_user):
    """Revoke endpoint sets PermissionGrant.is_active=False."""
    from django.contrib.auth.models import Permission

    perm = Permission.objects.filter(codename="view_customuser").first()
    PermissionGrant.objects.create(
        user=hr_limited_user, permission=perm, granted_by=hr_full_user, is_active=True
    )
    hr_limited_user.user_permissions.add(perm)

    api_client.force_authenticate(user=hr_full_user)
    resp = api_client.post(
        f"/api/v1/users/{hr_limited_user.id}/revoke-permission/",
        {"permission_codename": "view_customuser"},
        format="json",
    )
    assert resp.status_code == 200
    assert not PermissionGrant.objects.filter(
        user=hr_limited_user, permission=perm, is_active=True
    ).exists()


@pytest.mark.phase2
@pytest.mark.django_db
def test_regrant_revoked_permission_reactivates_grant(api_client, hr_full_user, hr_limited_user):
    """Re-granting a previously revoked permission reactivates the grant."""
    from django.contrib.auth.models import Permission

    perm = Permission.objects.filter(codename="view_customuser").first()
    grant = PermissionGrant.objects.create(
        user=hr_limited_user, permission=perm, granted_by=hr_full_user, is_active=False
    )

    api_client.force_authenticate(user=hr_full_user)
    api_client.post(
        f"/api/v1/users/{hr_limited_user.id}/grant-permission/",
        {"permission_codename": "view_customuser"},
        format="json",
    )
    grant.refresh_from_db()
    assert grant.is_active


@pytest.mark.phase2
@pytest.mark.django_db
def test_limited_user_cannot_grant_permission(api_client, hr_limited_user, active_user):
    """A user with permission_level=limited cannot grant permissions (403)."""
    api_client.force_authenticate(user=hr_limited_user)
    resp = api_client.post(
        f"/api/v1/users/{active_user.id}/grant-permission/",
        {"permission_codename": "view_customuser"},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.phase2
@pytest.mark.django_db
def test_md_can_grant_cross_department(api_client, md_user, finance_full_user):
    """MD can grant permissions across departments."""
    api_client.force_authenticate(user=md_user)
    resp = api_client.post(
        f"/api/v1/users/{finance_full_user.id}/grant-permission/",
        {"permission_codename": "view_customuser"},
        format="json",
    )
    assert resp.status_code == 200


# ── AuditLog edge cases ───────────────────────────────────────────────────────

@pytest.mark.phase2
@pytest.mark.django_db
def test_auditlog_is_read_only_via_api(api_client, md_user):
    """AuditLog is append-only: PUT and DELETE via API return 405."""
    AuditLog.log(action="test.action", user=md_user)
    log = AuditLog.objects.first()

    api_client.force_authenticate(user=md_user)
    assert api_client.put(f"/api/v1/audit-logs/{log.id}/", {}, format="json").status_code == 405
    assert api_client.delete(f"/api/v1/audit-logs/{log.id}/").status_code == 405


@pytest.mark.phase2
@pytest.mark.django_db
def test_md_can_read_audit_log(api_client, md_user):
    """md role can access GET /audit-logs/."""
    AuditLog.log(action="test.action", user=md_user)
    api_client.force_authenticate(user=md_user)
    resp = api_client.get("/api/v1/audit-logs/")
    assert resp.status_code == 200
    assert resp.data["count"] >= 1


@pytest.mark.phase2
@pytest.mark.django_db
def test_auditlog_csv_export(api_client, md_user):
    """GET /audit-logs/export/ returns a CSV file."""
    AuditLog.log(action="test.export", user=md_user)
    api_client.force_authenticate(user=md_user)
    resp = api_client.get("/api/v1/audit-logs/export/")
    assert resp.status_code == 200
    assert "text/csv" in resp["Content-Type"]
    content = b"".join(resp.streaming_content).decode() if hasattr(resp, "streaming_content") else resp.content.decode()
    assert "test.export" in content


# ── Notification model smoke test ─────────────────────────────────────────────

@pytest.mark.phase2
@pytest.mark.django_db
def test_notification_table_accepts_inserts(active_user):
    """Notification.objects.create() succeeds — table exists and is writable."""
    n = Notification.objects.create(
        recipient=active_user,
        notification_type="system",
        title="Test notification",
        body="Body text",
        channel="in_app",
    )
    assert n.id is not None
    assert not n.is_read
    assert Notification.objects.filter(pk=n.pk).exists()


@pytest.mark.phase2
@pytest.mark.django_db
def test_notification_recipient_isolation(active_user, hr_limited_user):
    """A notification for user A is not visible when querying for user B."""
    Notification.objects.create(
        recipient=active_user,
        notification_type="system",
        title="Only for active_user",
        body="private",
        channel="in_app",
    )
    assert not Notification.objects.filter(recipient=hr_limited_user).exists()


# ── mfa_secret encryption ─────────────────────────────────────────────────────

@pytest.mark.phase2
@pytest.mark.django_db
def test_mfa_secret_stored_encrypted_in_db(api_client, active_user):
    """Raw DB value of mfa_secret is not the plaintext TOTP secret."""
    from django.db import connection

    api_client.force_authenticate(user=active_user)
    resp = api_client.post("/api/v1/auth/mfa/setup/", format="json")
    plaintext_secret = resp.data["secret"]

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT mfa_secret FROM users_customuser WHERE id = %s",
            [str(active_user.id)],
        )
        raw_db_value = cursor.fetchone()[0]

    assert raw_db_value != plaintext_secret  # must be encrypted
    assert raw_db_value  # must not be empty
    # Verify the model decrypts it back correctly
    active_user.refresh_from_db()
    assert active_user.mfa_secret == plaintext_secret


# ── Group sync signal edge cases ──────────────────────────────────────────────

@pytest.mark.phase2
@pytest.mark.django_db
def test_signal_user_with_no_role_gets_no_group(django_user_model):
    """A user with role='' is not assigned to any group."""
    user = django_user_model.objects.create_user(
        username="norole", email="norole@example.com",
        password="Test1234!", is_active=True,
    )
    assert user.groups.count() == 0


@pytest.mark.phase2
@pytest.mark.django_db
def test_signal_single_level_roles_use_bare_group_name(django_user_model):
    """md, front_desk, content_creator get group names without _full/_limited suffix."""
    for role in ("md", "front_desk", "content_creator"):
        user = django_user_model.objects.create_user(
            username=f"signal_{role}",
            email=f"signal_{role}@example.com",
            password="Test1234!",
            role=role,
            is_active=True,
        )
        assert user.groups.filter(name=role).exists(), f"Expected group '{role}' for role '{role}'"
        assert not user.groups.filter(name__contains="_full").exists()
        assert not user.groups.filter(name__contains="_limited").exists()
