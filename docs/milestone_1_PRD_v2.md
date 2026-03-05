# CLAUDE CODE — IMPLEMENTATION PRD
## Milestone 1: Core Organizational Management System (v2)

> **Stack:** Dockerized Django REST API · PostgreSQL · Redis + Celery
> **API versioning:** `/api/v1/**` · **HTTP Methods:** GET / POST / PUT / DELETE
> **Workflow:** Build · Test · Check · Proceed

---

## Changes from v1

This document supersedes `milestone_1_PRD_and_Implementation_checklist.md` (v1, 804 lines).
All original models, endpoints, business logic, test IDs, and checklists are preserved.
The following structural fixes have been applied:

| Fix | Problem in v1 | Resolution in v2 |
|---|---|---|
| **Fix 1** | `Notification` model defined in Phase 7, but Phases 3–6 all insert notification rows. Phase 3 tests (e.g. APR-01) cannot pass if the table does not exist. | `Notification` moved to Phase 2 (alongside `AuditLog`). Phase 7 becomes API-only with beat schedule config. |
| **Fix 2** | Phase 6 header says "Dependency: Phase 5 complete" but `MaintenanceRequest.project` is an FK to `apps/projects/Project` (Phase 4 model). Migration fails without Phase 4. | Phase 6 dependency changed to "Phase 4 complete AND Phase 5 complete". |
| **Fix 3** | Master Gate demands "7 NFY tests" but Phase 7 defines zero test IDs. No way to verify the gate. | Phase 7 now defines NFY-01 through NFY-07 with explicit assertions. |
| **Fix 4** | `check_budget_alerts` (Phase 4) and `check_sla_breaches` (Phase 6) re-appear in Phase 7 beat table with no clarity on where `CELERY_BEAT_SCHEDULE` lives. | Phase 4 and Phase 6 note tasks are implemented there; `CELERY_BEAT_SCHEDULE` registration is owned by Phase 7 in `config/settings/base.py`. |
| **Fix 5** | No dependency graph. Reader cannot see that Phase 4 and Phase 5 are technically parallel. | True dependency graph added to section 0.0. Sequential order (1→2→3→4→5→6→7→8) is preserved by policy. |

---

## 0. How to Use This Document

This PRD is structured as a sequential build-test-check workflow. Claude Code works through one phase at a time. Each phase ends with a mandatory checklist. **Do not proceed to the next phase until every checkbox in the current phase is marked PASSED.**

> **Workflow Rule**
> Phase N code → Phase N tests run → Phase N checklist reviewed → ALL items green → proceed to Phase N+1.
> If any checklist item fails: fix → re-run tests → re-check before advancing.
> **Never skip a phase or merge incomplete work forward.**

### 0.0 True Phase Dependency Graph

```
Phase 1 (Infrastructure)
    └── Phase 2 (Auth + RBAC + AuditLog + Notification model)
            └── Phase 3 (Approval Engine)
                    ├── Phase 4 (Projects & Site Mgmt)   ← technically independent of Phase 5
                    └── Phase 5 (Shortlets & Bookings)   ← technically independent of Phase 4
                            └── Phase 6 (Maintenance)    ← requires BOTH Phase 4 AND Phase 5
                                    └── Phase 7 (Notification API + Full Beat Schedule)
                                                └── Phase 8 (Deploy Readiness)
```

> **Policy note:** Phase 4 and Phase 5 both depend only on Phase 3 and are theoretically parallelisable.
> Sequential ordering is enforced here to keep implementation focused and make checklists unambiguous.
> Phase 6 requires **both** Phase 4 (for `MaintenanceRequest.project` FK) and Phase 5 (for `MaintenanceRequest.property` FK).

---

## 0.1 Global Conventions

| Convention | Value |
|---|---|
| API base prefix | `/api/v1/` |
| Update method | `PUT` (not PATCH) for all resource updates |
| Auth header | `Authorization: Bearer <access_token>` |
| Content type | `application/json` (all requests and responses) |
| ID format | UUID4 for all primary keys |
| Timestamps | ISO 8601 UTC (e.g. `2026-03-05T14:30:00Z`) |
| Money fields | Decimal string in JSON, e.g. `"125000.00"` (avoid float) |
| Error envelope | `{"error": "code", "message": "...", "details": {...}}` |
| Success list | `{"count": N, "next": url\|null, "previous": url\|null, "results": [...]}` |
| HTTP 200 | GET success |
| HTTP 201 | POST success (resource created) |
| HTTP 204 | DELETE or action with no body returned |
| HTTP 400 | Validation error |
| HTTP 401 | Not authenticated |
| HTTP 403 | Authenticated but not permitted |
| HTTP 404 | Resource not found |
| HTTP 409 | Conflict (duplicate, double-booking, etc.) |

---

## 0.2 Project Structure Claude Code Must Generate

```
propms/                           # project root
├── docker-compose.yml
├── docker-compose.prod.yml
├── .env.example
├── Makefile                      # dev shortcuts
├── README.md
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── requirements.dev.txt
│   ├── manage.py
│   ├── config/                   # Django settings package
│   │   ├── __init__.py
│   │   ├── settings/
│   │   │   ├── base.py           # CELERY_BEAT_SCHEDULE lives here (owned by Phase 7)
│   │   │   ├── development.py
│   │   │   └── production.py
│   │   ├── urls.py               # root: /api/v1/ prefix
│   │   ├── wsgi.py
│   │   └── asgi.py
│   ├── apps/
│   │   ├── users/                # Auth, RBAC, Audit, Notification model
│   │   ├── approvals/            # Workflow engine
│   │   ├── projects/             # Projects, Milestones, Reports, Reqs
│   │   ├── shortlets/            # Assets, Clients, Bookings, Deposits
│   │   ├── maintenance/          # Maintenance requests
│   │   ├── notifications/        # Notification API endpoints + Celery tasks
│   │   └── core/                 # Shared models, mixins, utils
│   └── tests/
│       ├── conftest.py
│       ├── test_auth.py
│       ├── test_projects.py
│       ├── test_shortlets.py
│       └── test_maintenance.py
```

---

# Phase 1 — Docker & Project Scaffolding

> *Estimated effort: 0.5 day · No external dependencies · Foundation for all other phases*

## 1.1 Docker Compose Services

| Service | Image | Purpose | Ports |
|---|---|---|---|
| db | `postgres:15-alpine` | Primary PostgreSQL database | 5432 (internal) |
| redis | `redis:7-alpine` | Cache + Celery broker | 6379 (internal) |
| backend | Custom Dockerfile | Django + DRF API server | 8000:8000 |
| celery_worker | Same as backend | Async task processing | None |
| celery_beat | Same as backend | Periodic task scheduler | None |
| nginx | `nginx:alpine` | Reverse proxy (prod only) | 80:80, 443:443 |

## 1.2 Required Environment Variables (`.env.example`)

```bash
# Django
DJANGO_SECRET_KEY=changeme
DJANGO_SETTINGS_MODULE=config.settings.development
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DB_NAME=propms_db
DB_USER=propms_user
DB_PASSWORD=changeme
DB_HOST=db
DB_PORT=5432

# Redis
REDIS_URL=redis://redis:6379/0

# JWT
JWT_ACCESS_TOKEN_LIFETIME_MINUTES=15
JWT_REFRESH_TOKEN_LIFETIME_DAYS=7

# Email
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend  # dev
SENDGRID_API_KEY=
DEFAULT_FROM_EMAIL=noreply@propms.com

# Storage
USE_S3=False  # dev: local filesystem
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_STORAGE_BUCKET_NAME=

# Security
CORS_ALLOWED_ORIGINS=http://localhost:3000
FERNET_KEY=changeme  # 32-byte base64 for field encryption
```

## 1.3 Makefile Targets Claude Code Must Include

| Target | Command | Description |
|---|---|---|
| `make up` | `docker-compose up -d` | Start all dev services |
| `make down` | `docker-compose down` | Stop all services |
| `make migrate` | `docker-compose exec backend python manage.py migrate` | Run DB migrations |
| `make seed` | `docker-compose exec backend python manage.py seed_groups` | Create all Django Groups + permissions |
| `make test` | `docker-compose exec backend pytest --cov=apps --cov-report=term-missing` | Full test suite |
| `make test-phase N=1` | `pytest -m phase1 -v` | Run tests for specific phase |
| `make shell` | `docker-compose exec backend python manage.py shell_plus` | Django shell |
| `make logs` | `docker-compose logs -f backend` | Stream backend logs |
| `make lint` | `flake8 apps/ && black apps/ --check` | Lint check |
| `make createsuperuser` | `docker-compose exec backend python manage.py createsuperuser` | Create admin |

## 1.4 Phase 1 Checklist

| | Test / Task | Expected Result | Status |
|---|---|---|---|
| ☐ | `docker-compose up` starts all 4 dev services without errors | All containers Running | |
| ☐ | `docker-compose ps` shows db, redis, backend, celery_worker healthy | Health: healthy / Up | |
| ☐ | `GET http://localhost:8000/api/v1/` returns 200 with API info JSON | HTTP 200 JSON response | |
| ☐ | `.env.example` contains all required keys; `.env` is git-ignored | File present; .gitignore correct | |
| ☐ | `make migrate` runs all migrations with no errors | Exit code 0 | |
| ☐ | `make seed` creates all 13 Django Groups without errors | 13 groups in DB | |
| ☐ | `make test` runs and exits 0 (even if 0 tests yet — no import errors) | pytest exit 0 | |
| ☐ | `requirements.txt` pins all package versions (no bare package names) | All lines have `==version` | |
| ☐ | Dockerfile uses multi-stage build; no dev dependencies in prod image | Prod image < 400MB | |
| ☐ | `docker-compose.prod.yml` exists with nginx service and no `DEBUG=True` | File valid | |

---

# Phase 2 — Authentication, RBAC & Audit

> *App: `apps/users/` · Estimated effort: 3 days · Dependency: Phase 1 complete*

> **v2 note (Fix 1):** The `Notification` model is defined and migrated here alongside `AuditLog`.
> Both are system-wide tracking records needed by all subsequent phases.
> Phase 7 adds the API endpoints and completes the Celery beat schedule — no new migration in Phase 7.

## 2.1 Models to Implement

| Model | Key Fields | Notes |
|---|---|---|
| `CustomUser` | id(UUID), full_name, email(unique), phone(unique), role, department, permission_level, is_active, mfa_enabled, mfa_secret(encrypted), created_by, last_login_ip | Extends AbstractUser; email = USERNAME_FIELD |
| `EmailVerificationToken` | id(UUID), user(FK), token(64-char), expires_at, used_at(nullable) | Invalidated after first use OR expiry |
| `PermissionGrant` | id(UUID), user(FK), permission(FK auth.Permission), granted_by(FK), granted_at, is_active, revoked_by(FK nullable), revoked_at | Audit trail of individual permission overrides |
| `AuditLog` | id(UUID), user(FK nullable), role_snapshot, action, resource_type, resource_id, description, metadata(JSON), ip_address, timestamp | APPEND-ONLY. No update/delete at app layer |
| `Notification` | id(UUID), recipient(FK CustomUser), notification_type, title(200), body, resource_type(50 blank), resource_id(UUID nullable), channel, is_read(default False), read_at(nullable), created_at(auto) | `notification_type` choices: `approval_pending\|approval_decided\|assignment\|sla_warning\|budget_alert\|booking_reminder\|system`; `channel` choices: `in_app\|email\|sms` |

## 2.2 Management Command: `seed_groups`

Claude Code must implement a management command at `apps/users/management/commands/seed_groups.py` that creates all 13 Django Groups and assigns the correct Django model-level permissions to each. This command must be **idempotent** (safe to run multiple times).

| Group Name | Permissions Summary |
|---|---|
| `md` | All permissions across all models (superuser-equivalent via groups) |
| `hr_full` | add/change/view user, view auditlog, approve workflows, view all projects/bookings |
| `hr_limited` | view user (own dept), view projects, view bookings |
| `finance_full` | view/change payments, approve requisitions, process refunds |
| `finance_limited` | view payments, view requisitions |
| `admin_full` | add/change/view/delete shortlet properties, clients, bookings, maintenance requests |
| `admin_limited` | view shortlet properties, view clients, view bookings |
| `pm_full` | add/change/view projects, milestones, site reports, requisitions (own projects) |
| `pm_limited` | add site reports (own projects), view projects, view requisitions |
| `front_desk` | add/change/view clients, bookings; perform check-in/check-out |
| `social_media_full` | Full access to social/content module |
| `social_media_limited` | View-only social/content |
| `content_creator` | Add/view content assets |

## 2.3 API Endpoints

| Method | URL | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/auth/register/` | `can_create_user` | Create user; send verification email via Celery |
| POST | `/api/v1/auth/verify-email/` | Public | Consume token → activate user |
| POST | `/api/v1/auth/set-password/` | Public + token | First-time password setup |
| POST | `/api/v1/auth/login/` | Public | Returns `{access, refresh}`; logs IP+device to AuditLog |
| POST | `/api/v1/auth/token/refresh/` | Public | JWT refresh |
| POST | `/api/v1/auth/logout/` | JWT | Blacklist refresh token |
| POST | `/api/v1/auth/mfa/setup/` | JWT | Returns TOTP provisioning URI + backup codes |
| POST | `/api/v1/auth/mfa/verify/` | JWT (partial) | Complete MFA login; returns full JWT pair |
| GET | `/api/v1/users/` | `can_manage_users` | List; filter by role, dept, is_active |
| POST | `/api/v1/users/` | `can_create_user` | Create user account |
| GET | `/api/v1/users/{id}/` | `can_manage_users \| self` | |
| PUT | `/api/v1/users/{id}/` | `can_manage_users \| self(limited)` | Role change triggers group sync signal |
| POST | `/api/v1/users/{id}/grant-permission/` | `manager_same_dept` | Add individual permission; writes PermissionGrant |
| POST | `/api/v1/users/{id}/revoke-permission/` | `manager_same_dept` | Deactivate PermissionGrant + remove from user_permissions |
| GET | `/api/v1/users/{id}/permissions/` | `can_manage \| self` | Returns group perms + individual grants |
| GET | `/api/v1/users/me/` | JWT | Current user profile + effective permissions |
| PUT | `/api/v1/users/me/` | JWT | Update own name, phone, photo, notification prefs |
| GET | `/api/v1/audit-logs/` | `md \| hr_full` | Filterable; paginated |
| GET | `/api/v1/audit-logs/export/` | `md \| hr_full` | CSV download |

## 2.4 Business Logic Requirements

### Group Sync Signal (`post_save` on `CustomUser`)

```python
# signals.py
@receiver(post_save, sender=CustomUser)
def sync_user_group(sender, instance, **kwargs):
    instance.groups.clear()
    group, _ = Group.objects.get_or_create(name=instance.get_role_key())
    instance.groups.add(group)
    if instance.permission_level == "full":
        instance.user_permissions.clear()
        instance.granted_permissions.filter(is_active=True).update(is_active=False)
```

### Login Security

- Rate limit: **10 attempts per 15 minutes per IP** (use `django-ratelimit` or custom throttle).
- After 5 failures: lock account for 30 min; send unlock email via Celery.
- MFA mandatory for roles: `md`, `hr_full` — `mfa_enabled` must be `True` before full JWT issued.
- Every login writes AuditLog: `action=auth.login`, `metadata={ip, device, success}`.

## 2.5 Phase 2 Tests to Write

| Test ID | Test Description | Assertion |
|---|---|---|
| AUTH-01 | HR creates user → verification email sent (mock) → token created in DB | HTTP 201; token in DB; email task queued |
| AUTH-02 | Verify email with valid token → `user.is_active=True` | HTTP 200; `is_active=True` |
| AUTH-03 | Verify email with expired token → rejected | HTTP 400 |
| AUTH-04 | Login with correct credentials → JWT pair returned | HTTP 200; access+refresh present |
| AUTH-05 | Login with wrong password → 401; 5 failures → account locked | HTTP 401; HTTP 423 on 6th |
| AUTH-06 | Access protected endpoint without token → 401 | HTTP 401 |
| AUTH-07 | `hr_limited` tries to create user → 403 | HTTP 403 |
| AUTH-08 | Role changed to `hr_full` → user added to `hr_full` group, removed from `hr_limited` | Correct group membership |
| AUTH-09 | Promotion to full → individual grants deactivated | `PermissionGrant.is_active=False` |
| AUTH-10 | Manager grants permission to same-dept subordinate → `user.has_perm()` returns True | Permission active |
| AUTH-11 | Manager tries to grant permission to different-dept user → 403 | HTTP 403 |
| AUTH-12 | AuditLog entry created on login, user create, role change | 3 AuditLog rows created |
| AUTH-13 | `GET /api/v1/audit-logs/` by `hr_limited` → 403 | HTTP 403 |
| AUTH-14 | MFA setup → TOTP code validates → full JWT issued | HTTP 200 with full JWT |
| AUTH-15 | Logout → refresh token blacklisted → token/refresh returns 401 | HTTP 401 on reuse |

## 2.6 Phase 2 Checklist

| | Test / Task | Expected Result | Status |
|---|---|---|---|
| ☐ | All 5 models migrated (CustomUser, VerificationToken, PermissionGrant, AuditLog, **Notification**) | Migration exit 0 | |
| ☐ | `seed_groups` creates 13 groups; idempotent on re-run | 13 groups; no duplicates on 2nd run | |
| ☐ | `POST /api/v1/auth/register/` creates inactive user + queues email task | HTTP 201; Celery task visible | |
| ☐ | Email verification activates user and invalidates token | HTTP 200; `is_active=True`; `token.used_at` set | |
| ☐ | JWT login returns access + refresh tokens | HTTP 200; both tokens present | |
| ☐ | Protected routes reject missing/invalid JWT with 401 | HTTP 401 on all tested endpoints | |
| ☐ | Role change immediately updates group membership (no restart needed) | Group confirmed via `/users/{id}/permissions/` | |
| ☐ | PermissionGrant: manager can grant; non-manager cannot; cross-dept blocked | AUTH-10, AUTH-11 passing | |
| ☐ | Promotion clears individual grants | AUTH-09 passing | |
| ☐ | AuditLog written for: login, user_create, role_change, permission_grant | Rows visible in `/api/v1/audit-logs/` | |
| ☐ | `Notification` table exists and accepts inserts (smoke test) | `Notification.objects.create(...)` succeeds in shell | |
| ☐ | All 15 AUTH tests passing | `pytest -m phase2` → 15 passed, 0 failed | |
| ☐ | No N+1 queries on `GET /api/v1/users/` (use `select_related`) | Django Debug Toolbar: ≤ 5 queries | |
| ☐ | Sensitive field `mfa_secret` stored encrypted in DB | Raw DB value is not plaintext | |
| ☐ | Rate limiting active on `/auth/login/` (10 req/15min per IP) | HTTP 429 on 11th request | |

---

# Phase 3 — Approval Workflow Engine

> *App: `apps/approvals/` · Estimated effort: 2 days · Dependency: Phase 2 complete*

## 3.1 Models to Implement

| Model | Key Fields | Notes |
|---|---|---|
| `ApprovalWorkflow` | id, workflow_type, content_type(FK), object_id, status, initiated_by, l1_approver, l1_decision, l1_decided_at, l1_notes, l2_approver, l2_decision, l2_decided_at, l2_notes, requires_l2, withdrawn_at | Generic FK allows linking to Project, Requisition, or CautionDeposit |
| `ApprovalComment` | id, workflow(FK), author(FK), comment, comment_type(`comment\|info_request\|info_response`), created_at | Threaded discussion on any workflow |

## 3.2 Routing Rules (Enforced in Service Layer)

| workflow_type | L1 Actor | L2 Actor | L2 Condition |
|---|---|---|---|
| `project_proposal` | `hr_full` | `md` | Always required |
| `payment_requisition` | `hr_full` | `md` | amount > 500,000 OR amount > 20% of project remaining budget |
| `caution_refund` | `hr_full` | `md` | Always required |

> **Critical Business Rule**
> `requires_l2` is evaluated and stored at workflow creation time by the service layer.
> If the linked object amount changes before submission, `requires_l2` must be re-evaluated.
> Rejection at either level returns status to `"draft"` (not deleted) so initiator can revise and resubmit.
> Initiator can only withdraw if status is `pending_l1` or `pending_l2`.
> Rejection notes are mandatory (minimum 20 characters); enforce at serializer level.

## 3.3 Status State Machine

```
draft → pending_l1 → pending_l2 → approved
                ↓               ↓
            draft ←── rejected ←┘

pending_l1 or pending_l2 → withdrawn  (by initiator only)
```

## 3.4 API Endpoints

| Method | URL | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/approvals/` | JWT | My pending approvals + approvals I created; filterable by status, type |
| GET | `/api/v1/approvals/{id}/` | `participant \| md \| hr_full` | Full chain detail with comments |
| POST | `/api/v1/approvals/{id}/decide/` | `assigned_approver` | Body: `{decision: approved\|rejected\|more_info, notes: str}` |
| POST | `/api/v1/approvals/{id}/withdraw/` | `initiator` | Only if status `pending_l1` or `pending_l2` |
| POST | `/api/v1/approvals/{id}/comment/` | `participant` | Add comment or info request/response |
| GET | `/api/v1/approvals/pending-count/` | JWT | Returns `{count: N}` for dashboard badge |

## 3.5 Notifications on Approval Events

| Event | Notify Who | Channel |
|---|---|---|
| Submitted (pending_l1) | L1 approver | email + in-app |
| L1 approved (pending_l2) | L2 approver + initiator | email + in-app |
| L1 rejected (back to draft) | Initiator | email + in-app |
| L2 approved | Initiator + assigned PM (if project) | email + in-app |
| L2 rejected (back to draft) | Initiator + L1 approver | email + in-app |
| More info requested | Initiator | email + in-app |
| Withdrawn | L1 or L2 approver (whoever had it pending) | in-app |
| Pending > 24hr reminder | Current approver | email (Celery beat) |

## 3.6 Phase 3 Tests

| Test ID | Test Description | Assertion |
|---|---|---|
| APR-01 | Create `project_proposal` workflow → `status=pending_l1`; `hr_full` notified | HTTP 201; notification created |
| APR-02 | L1 approve → `status=pending_l2` (for project_proposal) | HTTP 200; status updated |
| APR-03 | L2 approve → `status=approved`; project activated | HTTP 200; `project.status=planning` |
| APR-04 | L1 reject without notes (< 20 chars) → 400 | HTTP 400 validation error |
| APR-05 | L1 reject with valid notes → `status=draft`; initiator notified | HTTP 200; `status=draft` |
| APR-06 | Initiator withdraws while `pending_l1` → `status=withdrawn` | HTTP 200 |
| APR-07 | Non-approver calls `/decide/` → 403 | HTTP 403 |
| APR-08 | Requisition ≤ 500K → `requires_l2=False`; only L1 needed | `requires_l2=False`; approved after L1 |
| APR-09 | Requisition > 500K → `requires_l2=True`; L2 required | `requires_l2=True`; `pending_l2` after L1 |
| APR-10 | `GET /pending-count/` returns correct badge number per role | Count matches DB query |

## 3.7 Phase 3 Checklist

| | Test / Task | Expected Result | Status |
|---|---|---|---|
| ☐ | `ApprovalWorkflow` and `ApprovalComment` models migrated | Migration exit 0 | |
| ☐ | Generic FK correctly links to Project, Requisition, CautionDeposit | ContentType FK works for all 3 | |
| ☐ | L1-only flow completes in ≤ 2 API calls (submit + decide) | APR-08 passing | |
| ☐ | L2 escalation triggered correctly for `project_proposal` and high-value requisitions | APR-02, APR-09 passing | |
| ☐ | Rejection returns item to draft with notes; initiator can resubmit | APR-05 passing; re-submit works | |
| ☐ | Withdrawal blocked after approval | HTTP 400 if `status=approved` | |
| ☐ | Notifications sent via Celery task (not synchronously blocking the view) | Task visible in Celery logs | |
| ☐ | Pending > 24h reminder task exists; will be registered in beat schedule in Phase 7 | Task function defined in `apps/approvals/tasks.py` | |
| ☐ | All 10 APR tests passing | `pytest -m phase3` → 10 passed, 0 failed | |
| ☐ | `GET /approvals/` response time < 300ms with 100 workflows in DB | django-silk or logs confirm | |

---

# Phase 4 — Project & Site Management

> *App: `apps/projects/` · Estimated effort: 4 days · Dependency: Phase 3 complete*

> **v2 note (Fix 4):** `check_budget_alerts` Celery task is implemented in this phase in
> `apps/projects/tasks.py`. It is **not** registered in `CELERY_BEAT_SCHEDULE` until Phase 7,
> which owns all beat schedule configuration in `config/settings/base.py`.

## 4.1 Models to Implement

| Model | Critical Fields | Auto-logic |
|---|---|---|
| `Project` | id, project_code(auto), name(unique), project_type, location_text, lat/lng, start_date, expected_end_date, budget_total, scope, status, health, progress_pct, progress_manual_override, project_manager(FK), created_by(FK) | `project_code` generated on L2 approval: `PROJ-YYYY-NNN` using DB sequence |
| `ProjectBudgetLine` | id, project(FK), category, allocated_amount, committed_amount, spent_amount | `remaining = allocated - (committed + spent)`; recalculate on every requisition approval/payment |
| `ProjectDocument` | id, project(FK), file(S3 key), original_filename, file_size_bytes, uploaded_by(FK) | Min 1 doc required before proposal submission |
| `ProjectMilestone` | id, project(FK), title, target_date, actual_completion_date, status, depends_on(self-FK) | On milestone save: if `progress_manual_override=False`, recalculate `project.progress_pct` |
| `SiteReport` | id, project(FK), report_date(≤today), report_type, task_description(200), progress_summary(1000), completion_pct_added, external_labor_count, weather_condition, has_safety_incident, incident_description, is_locked(always True) | Locked on creation; addendum model for amendments |
| `SiteReportMaterial` | id, report(FK), material_name, opening_balance, new_deliveries, quantity_used, closing_balance(auto), wastage, unit, work_area | `closing_balance = opening + deliveries - used`; `quantity_used` cannot exceed available |
| `Requisition` | id, req_code(auto), project(FK nullable), budget_line(FK), category, urgency, description(500), total_amount, payment_structure, mobilization_pct, mobilization_amount, balance_terms, vendor_name, status, mobilization_status, balance_status, created_by(FK) | `req_code: REQ-YYYY-NNNN`; triggers `ApprovalWorkflow` on submit |
| `RequisitionLineItem` | id, requisition(FK), description, quantity, unit_of_measure, unit_cost, total_cost(auto) | `total_cost = quantity * unit_cost`; sum of line items = `requisition.total_amount` |

## 4.2 Project Status State Machine

```
draft → pending_l1 → pending_l2 → approved → planning → in_progress → on_hold → completed
                                                                              ↓
                                                                          cancelled

Health (separate field, auto-updated by Celery task):
  not_started | on_track | at_risk (≤7 days to deadline) | delayed (past deadline) | completed
```

## 4.3 API Endpoints

| Method | URL | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/projects/` | authenticated | Filter: status, type, pm, date_range; sortable |
| POST | `/api/v1/projects/` | `md\|admin\|pm` | Create project (defaults to draft) |
| GET | `/api/v1/projects/{id}/` | authenticated | Full project detail |
| PUT | `/api/v1/projects/{id}/` | creator (draft only) | Blocked if `status != draft` |
| POST | `/api/v1/projects/{id}/submit/` | creator | Draft → pending_l1; creates ApprovalWorkflow |
| GET | `/api/v1/projects/{id}/budget/` | authenticated | Budget breakdown + utilization % |
| GET | `/api/v1/projects/{id}/milestones/` | authenticated | |
| POST | `/api/v1/projects/{id}/milestones/` | `pm_on_project` | Creates milestone |
| PUT | `/api/v1/projects/{id}/milestones/{mid}/` | `pm_on_project` | Status update recalculates `progress_pct` |
| GET | `/api/v1/projects/{id}/documents/` | authenticated | |
| POST | `/api/v1/projects/{id}/documents/` | creator (draft) | Multipart upload; stores S3 key |
| GET | `/api/v1/projects/{id}/site-reports/` | authenticated | |
| POST | `/api/v1/projects/{id}/site-reports/` | `pm_on_project` | Material reconciliation validated |
| GET | `/api/v1/projects/{id}/site-reports/{rid}/` | authenticated | |
| GET | `/api/v1/projects/{id}/site-reports/{rid}/pdf/` | authenticated | Returns PDF (WeasyPrint/reportlab) |
| GET | `/api/v1/projects/{id}/requisitions/` | authenticated | |
| POST | `/api/v1/projects/{id}/requisitions/` | `pm\|admin` | Creates requisition; validates budget impact |
| PUT | `/api/v1/projects/{id}/requisitions/{rid}/` | creator (draft only) | |
| POST | `/api/v1/projects/{id}/requisitions/{rid}/submit/` | creator | Triggers approval workflow |
| GET | `/api/v1/projects/dashboard/` | `md\|pm_full` | Aggregated KPI cards (cached 60s) |

## 4.4 Budget Alert Logic (Celery Tasks)

- `check_budget_alerts` implemented in `apps/projects/tasks.py`; **registered in `CELERY_BEAT_SCHEDULE` in Phase 7**.
- Runs hourly; scans all active `ProjectBudgetLine` records.
- On first crossing of **80%** utilization: create Notification for PM + MD; write to AuditLog.
- On first crossing of **95%** utilization: create CRITICAL Notification for MD; write to AuditLog.
- Track `alerts_sent` as a `JSONField` on `ProjectBudgetLine` to avoid duplicate alerts.
- When an approved Requisition is linked to a budget line, `committed_amount` is incremented atomically using `F()` expressions.

## 4.5 Phase 4 Tests

| Test ID | Test Description | Assertion |
|---|---|---|
| PROJ-01 | PM creates project → `status=draft`; `project_code` is null until approval | HTTP 201; `project_code=null` |
| PROJ-02 | Submit project → `ApprovalWorkflow` created; `status=pending_l1` | HTTP 200; workflow in DB |
| PROJ-03 | Full L1+L2 approval → `project_code` assigned (`PROJ-YYYY-NNN` format); `status=planning` | code matches regex |
| PROJ-04 | Edit project after submission → 400 | HTTP 400 |
| PROJ-05 | Milestone completed → `progress_pct` auto-updated (if not manual override) | `progress_pct` recalculated |
| PROJ-06 | Manual override set → milestone completion does NOT change `progress_pct` | `progress_pct` unchanged |
| PROJ-07 | Site report with `quantity_used > opening + deliveries` → 400 | HTTP 400 |
| PROJ-08 | Site report submitted → `is_locked=True`; PUT blocked | HTTP 405 or 400 |
| PROJ-09 | Requisition ≤ 500K submitted → `requires_l2=False` | `WorkFlow.requires_l2=False` |
| PROJ-10 | Requisition > 500K submitted → `requires_l2=True` | `Workflow.requires_l2=True` |
| PROJ-11 | Approved requisition → `budget_line.committed_amount` incremented by req amount | F() update confirmed |
| PROJ-12 | Budget utilization > 80% → notification created for PM and MD | 2 Notification rows created |
| PROJ-13 | `GET /projects/dashboard/` cached; second call does not hit DB | Cache hit in Redis |
| PROJ-14 | PDF generation for site report returns valid PDF bytes | `Content-Type: application/pdf` |
| PROJ-15 | `pm_limited` cannot create project; can create site report on assigned project | HTTP 403 + HTTP 201 |

## 4.6 Phase 4 Checklist

| | Test / Task | Expected Result | Status |
|---|---|---|---|
| ☐ | All 8 models migrated; no migration conflicts | Migration exit 0 | |
| ☐ | `project_code` uses DB sequence (no COUNT+1); concurrent creation produces unique codes | No duplicate codes under load | |
| ☐ | Project edit blocked after submission | PROJ-04 passing | |
| ☐ | Progress auto-calculation works; manual override respected | PROJ-05, PROJ-06 passing | |
| ☐ | Material reconciliation enforced in site report (can't use more than available) | PROJ-07 passing | |
| ☐ | Site reports locked on creation; addendum endpoint exists | PROJ-08 passing | |
| ☐ | Requisition approval increments `committed_amount` atomically | PROJ-11 passing | |
| ☐ | Budget alerts sent without duplication on re-runs | PROJ-12; no duplicate notifications on 2nd Celery run | |
| ☐ | Dashboard endpoint cached in Redis; cache invalidated on project status change | PROJ-13 passing | |
| ☐ | PDF endpoint returns valid PDF | PROJ-14 passing | |
| ☐ | `check_budget_alerts` task function implemented in `apps/projects/tasks.py` | Function importable; not yet in beat schedule | |
| ☐ | All 15 PROJ tests passing | `pytest -m phase4` → 15 passed, 0 failed | |
| ☐ | `GET /projects/` with 50 projects responds in < 500ms | Response time logged | |

---

# Phase 5 — Shortlets & Asset Management

> *App: `apps/shortlets/` · Estimated effort: 3 days · Dependency: Phase 3 complete*

## 5.1 Models to Implement

| Model | Critical Fields | Auto-logic |
|---|---|---|
| `ShortletProperty` | id, property_code(auto `PROP-SL-NNN`), name, unit_type, location, rate_nightly, rate_weekly, rate_monthly, amenities(JSON array), description(1000), caution_deposit_amount, status | `status` auto-set to `occupied` during booking, `available` on checkout |
| `Client` | id, client_code(auto `CLT-NNNN`), full_name, email(unique nullable), phone(unique), id_type, id_number, client_type, is_vip, preferences_notes, created_by(FK) | Duplicate detection: email OR phone match → warn before create |
| `Booking` | id, booking_code(auto `BKG-YYYY-NNNN`), client(FK), property(FK), check_in_date, check_out_date, rate_type, num_guests, base_amount(auto), caution_deposit, total_amount(auto), payment_method, payment_reference, status, checked_in_at, checked_out_at, checkout_condition, created_by(FK) | Double-booking prevention via `SELECT FOR UPDATE`; `base_amount` auto-calculated from dates + rate |
| `BookingReceipt` | id, booking(OneToOne), receipt_number(auto `RCP-YYYY-NNNN`), pdf_file(S3 key), generated_at, generated_by(FK) | Generated async via Celery after booking confirmed; immutable after creation |
| `CautionDeposit` | id, booking(OneToOne), deposit_amount, deduction_amount(default 0), deduction_reason, refund_amount(auto), refund_method, account_number(encrypted), status, initiated_by(FK), processed_by(FK nullable) | Auto-created at booking creation with `status=held`; `refund_amount = deposit - deduction` |

## 5.2 API Endpoints

| Method | URL | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/properties/` | authenticated | Filter: type, status, price_min, price_max |
| POST | `/api/v1/properties/` | `admin\|front_desk` | |
| GET | `/api/v1/properties/{id}/` | authenticated | Includes upcoming reservations, maintenance history |
| PUT | `/api/v1/properties/{id}/` | `admin\|front_desk` | |
| GET | `/api/v1/properties/{id}/availability/` | authenticated | Returns `[{check_in, check_out}]` blocked ranges |
| GET | `/api/v1/clients/` | `admin\|front_desk` | Search by name, email, phone (icontains) |
| POST | `/api/v1/clients/` | `admin\|front_desk` | Runs duplicate check; returns 409 if duplicate found and not force-confirmed |
| GET | `/api/v1/clients/{id}/` | `admin\|front_desk` | Includes booking history, deposits, notes |
| PUT | `/api/v1/clients/{id}/` | `admin\|front_desk` | |
| GET | `/api/v1/clients/export/` | `md\|admin_full` | CSV; excludes `id_number` field |
| GET | `/api/v1/bookings/` | `admin\|front_desk\|md\|hr_full` | Filter: status, date_range, property |
| POST | `/api/v1/bookings/` | `admin\|front_desk` | Availability check → create → receipt task queued |
| GET | `/api/v1/bookings/{id}/` | `admin\|front_desk\|md` | |
| POST | `/api/v1/bookings/{id}/check-in/` | `admin\|front_desk` | `status→checked_in`; log timestamp |
| POST | `/api/v1/bookings/{id}/check-out/` | `admin\|front_desk` | Body: `{condition, deduction_amount, notes}`; triggers CautionDeposit refund |
| GET | `/api/v1/bookings/{id}/receipt/` | `admin\|front_desk` | Returns PDF; 404 if not yet generated |
| GET | `/api/v1/deposits/` | `admin\|hr_full\|md` | Filter: status |
| PUT | `/api/v1/deposits/{id}/` | `admin` | Set refund method + bank details; triggers ApprovalWorkflow |

> **Availability Check Implementation**
> Use `SELECT FOR UPDATE` on the property row inside a DB transaction.
> ```python
> Booking.objects.select_for_update().filter(
>     property=property,
>     status__in=["confirmed", "checked_in"],
>     check_in_date__lt=requested_checkout,
>     check_out_date__gt=requested_checkin
> )
> ```
> If any result: return HTTP 409 `{"error": "property_unavailable", "message": "Property is booked for these dates"}`

## 5.3 Receipt PDF Fields

- **Header:** Company logo, company name, address, receipt number, date
- **Client:** Full name, phone, email, ID type
- **Property:** Name, type, location, property code
- **Booking:** Check-in date, check-out date, duration, rate type
- **Charges:** Base amount breakdown, caution deposit, total paid
- **Payment:** Method, reference number, payment date
- **Footer:** "Thank you" note, QR code linking to booking reference

## 5.4 Phase 5 Tests

| Test ID | Test Description | Assertion |
|---|---|---|
| SHL-01 | Create property → `property_code` auto-assigned `PROP-SL-NNN` | HTTP 201; code matches regex |
| SHL-02 | Create client → `CLT-NNNN` assigned; duplicate phone returns 409 | HTTP 201; 409 on duplicate |
| SHL-03 | Create booking → availability checked; double-booking rejected | HTTP 201 first; HTTP 409 second |
| SHL-04 | Concurrent bookings (2 simultaneous requests) → only 1 succeeds | HTTP 201 + HTTP 409; no double-booking in DB |
| SHL-05 | Booking created → `CautionDeposit` auto-created with `status=held` | `CautionDeposit` row exists |
| SHL-06 | Booking created → receipt Celery task queued; PDF accessible after task runs | GET receipt returns PDF |
| SHL-07 | Check-in → `status=checked_in`; `checked_in_at` set | HTTP 200; timestamp set |
| SHL-08 | Check-out (good condition) → `status=checked_out`; `property.status=available`; refund workflow created | HTTP 200; workflow `pending_l1` |
| SHL-09 | Check-out (damaged, deduction) → `refund_amount = deposit - deduction`; workflow created | Correct `refund_amount` |
| SHL-10 | Caution refund approval (L1+L2) → `status=approved_for_refund`; client notified | Both approvals work; notification created |
| SHL-11 | `GET /properties/{id}/availability/` returns correct blocked ranges | Confirmed booking dates appear as blocked |
| SHL-12 | Client export CSV excludes `id_number` column (privacy) | CSV has no `id_number` column |
| SHL-13 | `front_desk` cannot access `/clients/export/` (admin_full only) | HTTP 403 |

## 5.5 Phase 5 Checklist

| | Test / Task | Expected Result | Status |
|---|---|---|---|
| ☐ | All 5 models migrated; `CautionDeposit` OneToOne with `Booking` enforced | Migration exit 0 | |
| ☐ | Double-booking prevented under concurrent load (`SELECT FOR UPDATE`) | SHL-04 passing | |
| ☐ | `CautionDeposit` auto-created on every booking | SHL-05 passing | |
| ☐ | Receipt PDF generated by Celery task; correct fields populated | SHL-06 passing | |
| ☐ | Check-out triggers caution refund approval workflow automatically | SHL-08, SHL-09 passing | |
| ☐ | `account_number` stored encrypted in DB | Raw DB value is not plaintext | |
| ☐ | Client CSV export excludes sensitive fields | SHL-12 passing | |
| ☐ | Property status auto-updated to `occupied` on check-in, `available` on check-out | status transitions correct | |
| ☐ | All 13 SHL tests passing | `pytest -m phase5` → 13 passed, 0 failed | |
| ☐ | Booking receipt PDF matches design spec (logo, all fields, QR code) | Manual visual check | |

---

# Phase 6 — Maintenance & Issue Escalation

> *App: `apps/maintenance/` · Estimated effort: 2 days · **Dependency: Phase 4 complete AND Phase 5 complete***

> **v2 note (Fix 2):** Phase 6 requires both Phase 4 AND Phase 5 because:
> - `MaintenanceRequest.project` → FK to `apps/projects/Project` (Phase 4 model)
> - `MaintenanceRequest.property` → FK to `apps/shortlets/ShortletProperty` (Phase 5 model)
> Migration will fail if either Phase 4 or Phase 5 has not run.

> **v2 note (Fix 4):** `check_sla_breaches` Celery task is implemented in this phase in
> `apps/maintenance/tasks.py`. It is **not** registered in `CELERY_BEAT_SCHEDULE` until Phase 7.

## 6.1 Models to Implement

| Model | Critical Fields | Auto-logic |
|---|---|---|
| `MaintenanceRequest` | id, request_code(auto `MNT-YYYY-NNNN`), issue_type, location_type, property(FK null → `apps/shortlets/ShortletProperty`), project(FK null → `apps/projects/Project`), location_details, priority, description(1000), status, reported_by(FK), assigned_to(FK null), assigned_by(FK null), assignment_notes, expected_resolution_at, resolved_at, closed_at, closed_by(FK null), resolution_notes, labor_hours, parts_cost, sla_deadline(auto), is_overdue(default False) | `sla_deadline = reported_at + SLA duration by priority`; `is_overdue` set by Celery beat task |
| `MaintenancePhoto` | id, request(FK), file(S3 key), caption(100), uploaded_at | Max 10 photos per request; 20MB total enforced at serializer |
| `MaintenanceStatusUpdate` | id, request(FK), from_status, to_status, updated_by(FK), notes, parts_needed(JSON), parts_vendor, parts_estimated_cost, parts_expected_delivery, timestamp | Append-only; no updates or deletes |

## 6.2 SLA Deadlines

| Priority | SLA Target | `sla_deadline` Calculation | Overdue Alert Sent To |
|---|---|---|---|
| Critical | 4 hours | `reported_at + 4 hours` | Admin + MD immediately on creation; Celery flags overdue at 4h |
| High | 24 hours | `reported_at + 24 hours` | Admin; Celery flags overdue at 24h |
| Medium | 72 hours | `reported_at + 72 hours` | Admin; Celery flags overdue at 72h |
| Low | 7 days | `reported_at + 168 hours` | Admin; Celery flags overdue at 7d |

## 6.3 Status State Machine

```
open → assigned → in_progress → pending_parts → resolved → closed
           ↓
         open  (if assignee declines)
```

## 6.4 API Endpoints

| Method | URL | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/maintenance/` | authenticated | Filter: status, priority, type, assignee, date |
| POST | `/api/v1/maintenance/` | `admin\|front_desk\|pm` | Create; calculates `sla_deadline`; sends priority-based alerts |
| GET | `/api/v1/maintenance/{id}/` | `participant\|admin\|md` | Full detail with status timeline |
| PUT | `/api/v1/maintenance/{id}/` | admin (open only) | Edit description/priority before assignment |
| POST | `/api/v1/maintenance/{id}/assign/` | admin | Body: `{assigned_to, notes, expected_resolution_at}` |
| POST | `/api/v1/maintenance/{id}/accept/` | assignee | Body: `{accepted: true\|false, decline_reason: str}` |
| POST | `/api/v1/maintenance/{id}/update-status/` | `assignee\|admin` | Creates `MaintenanceStatusUpdate`; updates status |
| POST | `/api/v1/maintenance/{id}/close/` | `admin\|front_desk` | Body: `{verification_notes}`; calculates resolution time |
| GET | `/api/v1/maintenance/metrics/` | `admin\|md` | Avg resolution time by type/priority; SLA breach rate |

## 6.5 Celery Task: `check_sla_breaches`

- Implemented in `apps/maintenance/tasks.py`; **registered in `CELERY_BEAT_SCHEDULE` in Phase 7**.
- Query: `MaintenanceRequest.objects.filter(status__in=["open","assigned","in_progress","pending_parts"], sla_deadline__lt=now(), is_overdue=False)`
- For each result: set `is_overdue=True`; create Notification for admin + MD; write AuditLog.
- Do **NOT** re-alert on already-overdue items (`is_overdue=True` check prevents spam).

## 6.6 Phase 6 Tests

| Test ID | Test Description | Assertion |
|---|---|---|
| MNT-01 | Create Critical request → `sla_deadline = reported_at + 4h`; immediate alert created | HTTP 201; notification created |
| MNT-02 | Create High request → `sla_deadline = reported_at + 24h` | deadline matches |
| MNT-03 | Assign request → `status=assigned`; assignee notified | HTTP 200; notification created |
| MNT-04 | Assignee accepts → status remains `assigned`; comment logged | HTTP 200 |
| MNT-05 | Assignee declines → `status=open`; admin notified for reassignment | HTTP 200; `status=open` |
| MNT-06 | Update to `in_progress` → `MaintenanceStatusUpdate` created; timestamp set | HTTP 200; update row in DB |
| MNT-07 | Update to `pending_parts` with parts JSON → parts stored correctly | HTTP 200; `parts_needed` JSON valid |
| MNT-08 | Close request → resolution time calculated; `status=closed` | HTTP 200; `resolved_at` set |
| MNT-09 | Overdue task: mock `sla_deadline` in past → `is_overdue=True` set; notification created | Celery task sets `is_overdue`; notification exists |
| MNT-10 | Re-run overdue task on same request → no duplicate notification (`is_overdue` already True) | No new notification created |
| MNT-11 | `GET /maintenance/metrics/` returns avg resolution time per priority | HTTP 200; correct structure |
| MNT-12 | Photos: more than 10 photos in one request → 400 | HTTP 400 |

## 6.7 Phase 6 Checklist

| | Test / Task | Expected Result | Status |
|---|---|---|---|
| ☐ | All 3 models migrated; Phase 4 and Phase 5 migrations confirmed present | Migration exit 0; no missing FK targets | |
| ☐ | Status updates append-only (no update/delete on `MaintenanceStatusUpdate`) | 405 on `PUT /status-updates/{id}/` | |
| ☐ | `sla_deadline` auto-calculated correctly for all 4 priority levels | MNT-01, MNT-02 passing | |
| ☐ | Decline flow returns request to open and notifies admin | MNT-05 passing | |
| ☐ | Celery SLA breach task sets `is_overdue` without duplicating alerts | MNT-09, MNT-10 passing | |
| ☐ | Photo upload enforces 10-file and 20MB limits | MNT-12 passing | |
| ☐ | Metrics endpoint returns correct aggregates | MNT-11 passing | |
| ☐ | `check_sla_breaches` task function implemented in `apps/maintenance/tasks.py` | Function importable; not yet in beat schedule | |
| ☐ | All 12 MNT tests passing | `pytest -m phase6` → 12 passed, 0 failed | |

---

# Phase 7 — Notification API Endpoints & Complete Celery Beat Schedule

> *App: `apps/notifications/` · Estimated effort: 1.5 days · Dependency: Phase 6 complete*

> **v2 note (Fix 1):** The `Notification` model was migrated in Phase 2.
> This phase adds the API layer and completes `CELERY_BEAT_SCHEDULE` in `config/settings/base.py`.
> **No new model migration is required in Phase 7.**

> **v2 note (Fix 4):** Phase 7 is the single owner of `CELERY_BEAT_SCHEDULE`.
> All 7 tasks (including `check_budget_alerts` from Phase 4 and `check_sla_breaches` from Phase 6)
> are registered here for the first time.

## 7.1 Celery Beat Schedule

Register all 7 tasks in `CELERY_BEAT_SCHEDULE` inside `config/settings/base.py`:

| Task Name | Implemented In | Schedule | Description |
|---|---|---|---|
| `check_sla_breaches` | `apps/maintenance/tasks.py` | Every 30 min | Flag overdue maintenance; send alerts |
| `check_budget_alerts` | `apps/projects/tasks.py` | Every 1 hour | Detect 80%/95% utilization; send once per threshold crossing |
| `booking_checkin_reminder` | `apps/notifications/tasks.py` | Daily 8:00 AM | Notify Front Desk of tomorrow's check-ins |
| `project_deadline_alert` | `apps/notifications/tasks.py` | Daily 9:00 AM | Notify PM + MD of projects due within 7 days |
| `pending_approval_reminder` | `apps/approvals/tasks.py` | Every 4 hours | Remind approvers of items pending > 24h |
| `dashboard_cache_refresh` | `apps/projects/tasks.py` | Every 60 seconds | Rebuild Redis cache keys for dashboard KPIs |
| `audit_log_archive` | `apps/users/tasks.py` | Monthly (1st, 3:00 AM) | Archive audit logs older than 7 years to cold storage |

## 7.2 In-App Notification API Endpoints

| Method | URL | Description |
|---|---|---|
| GET | `/api/v1/notifications/` | List my notifications; filter by `is_read`, type; paginated |
| POST | `/api/v1/notifications/{id}/read/` | Mark single notification as read |
| POST | `/api/v1/notifications/read-all/` | Mark all my notifications as read |
| GET | `/api/v1/notifications/unread-count/` | Returns `{count: N}` for UI badge |

## 7.3 Phase 7 Tests

| Test ID | Test Description | Assertion |
|---|---|---|
| NFY-01 | `GET /api/v1/notifications/unread-count/` returns correct unread count for authenticated user | `{"count": N}` matches unread rows for that recipient |
| NFY-02 | `POST /api/v1/notifications/{id}/read/` marks notification read → unread count decrements by 1 | `is_read=True`; `read_at` set; count decrements |
| NFY-03 | `POST /api/v1/notifications/read-all/` → all current user's unread notifications marked read | All `is_read=True` for that recipient; count = 0 |
| NFY-04 | User A cannot see User B's notifications on `GET /api/v1/notifications/` | Response contains only User A's rows; User B's rows absent |
| NFY-05 | `check_sla_breaches` Celery task called with overdue request → `Notification` row created for admin + MD | 2 `Notification` rows in DB with correct `recipient` and `notification_type=sla_warning` |
| NFY-06 | `check_budget_alerts` Celery task called with >80% utilised budget line → `Notification` row created | `Notification` row with `notification_type=budget_alert` and correct `resource_id` |
| NFY-07 | Email notification triggered by `approval_decided` event → email content visible in console backend | Console output contains recipient email and correct subject; no SMTP error |

## 7.4 Phase 7 Checklist

| | Test / Task | Expected Result | Status |
|---|---|---|---|
| ☐ | `Notification` model confirmed present (migrated in Phase 2) — no new migration needed | `python manage.py showmigrations` shows Phase 2 migration with Notification | |
| ☐ | All 7 Celery beat tasks registered in `CELERY_BEAT_SCHEDULE` in `config/settings/base.py` | `celery inspect scheduled` shows all 7 tasks | |
| ☐ | Celery worker processes all 7 tasks without crashing (run each task manually once) | No exceptions in Celery logs | |
| ☐ | In-app notification API returns only current user's notifications | `GET /notifications/` filtered by recipient — NFY-04 passing | |
| ☐ | Unread count updates correctly after mark-read and mark-all-read | NFY-01, NFY-02, NFY-03 passing | |
| ☐ | `check_sla_breaches` task creates Notification rows (not just sets `is_overdue`) | NFY-05 passing | |
| ☐ | `check_budget_alerts` task creates Notification rows with correct type and resource_id | NFY-06 passing | |
| ☐ | Email notifications sent for `approval_decided` event visible in console | NFY-07 passing | |
| ☐ | All notification tasks are async (never block API response) | API response < 200ms even when email is slow | |
| ☐ | All 7 NFY tests passing | `pytest -m phase7` → 7 passed, 0 failed | |

---

# Phase 8 — Deployment Readiness & Security Hardening

> *Estimated effort: 1.5 days · Dependency: All phases 1–7 complete and passing*

## 8.1 Production Docker Compose Checklist

| | Test / Task | Expected Result | Status |
|---|---|---|---|
| ☐ | `docker-compose.prod.yml` has nginx service with SSL termination config | nginx config valid | |
| ☐ | `DJANGO_SETTINGS_MODULE=config.settings.production` in prod compose | `DEBUG=False` in prod | |
| ☐ | Gunicorn used (not `runserver`) in prod container | CMD includes `gunicorn` | |
| ☐ | Static files collected and served by nginx (`STATIC_ROOT` configured) | `collectstatic` runs in Dockerfile | |
| ☐ | Media files served from S3 (`USE_S3=True` in prod env) | File upload goes to S3 | |
| ☐ | PostgreSQL connection uses SSL in production | `DB_SSL=require` in prod env | |
| ☐ | Redis password set in production | Redis AUTH configured | |
| ☐ | All secrets in environment variables; no hardcoded secrets in codebase | `git grep` finds no hardcoded keys | |

## 8.2 Security Checklist

| | Test / Task | Expected Result | Status |
|---|---|---|---|
| ☐ | CORS: `CORS_ALLOWED_ORIGINS` set to frontend domain only (no wildcard `*`) | No `*` in CORS config | |
| ☐ | JWT: access token = 15 min TTL; refresh = 7 days; refresh blacklisting enabled | Settings confirmed | |
| ☐ | Rate limiting on `/auth/login/`: 10 req / 15 min per IP | HTTP 429 on 11th attempt | |
| ☐ | `mfa_secret` and `account_number` fields encrypted at rest (Fernet) | Raw DB values are ciphertext | |
| ☐ | All file uploads validated for type (whitelist) and size limits | Invalid type returns 400 | |
| ☐ | `AuditLog` table has no UPDATE or DELETE permissions for app DB user | ALTER TABLE in migration; test fails if UPDATE attempted | |
| ☐ | Django CSRF protection enabled for session auth (API uses JWT, but admin panel uses session) | Admin panel CSRF working | |
| ☐ | `SECRET_KEY` is min 50 chars; not default value; different per environment | Length check in settings | |
| ☐ | SQL injection: all DB access via ORM; no raw SQL with user input | grep for `raw()` and `extra()` reviewed | |
| ☐ | Passwords: min 8 chars, at least 1 uppercase, 1 number, 1 special char enforced | `AUTH_PASSWORD_VALIDATORS` configured | |

## 8.3 Test Coverage Checklist

| | Test / Task | Expected Result | Status |
|---|---|---|---|
| ☐ | Overall test coverage ≥ 80% (pytest-cov report) | Coverage report shows ≥ 80% | |
| ☐ | All 15 AUTH tests passing | `pytest -m phase2` | |
| ☐ | All 10 APR tests passing | `pytest -m phase3` | |
| ☐ | All 15 PROJ tests passing | `pytest -m phase4` | |
| ☐ | All 13 SHL tests passing | `pytest -m phase5` | |
| ☐ | All 12 MNT tests passing | `pytest -m phase6` | |
| ☐ | All 7 NFY tests passing | `pytest -m phase7` | |
| ☐ | No test uses `print()` statements or `sleep()` (use `freeze_gun` for time mocking) | grep confirms | |
| ☐ | All tests use test database; no test modifies production-like fixtures | `pytest -p no:randomly` still passes | |
| ☐ | CI/CD pipeline runs tests on every push (GitHub Actions or equivalent) | Pipeline green | |

## 8.4 Performance Checklist

| | Test / Task | Expected Result | Status |
|---|---|---|---|
| ☐ | `GET /api/v1/projects/` with 50 records < 300ms (check with django-silk) | Response time logged | |
| ☐ | `GET /api/v1/bookings/` with 100 records < 300ms | Response time logged | |
| ☐ | Dashboard endpoint reads from Redis cache (not DB) on 2nd call | Cache hit confirmed | |
| ☐ | No endpoint produces > 10 DB queries (checked via DEBUG logging) | Query count ≤ 10 | |
| ☐ | File uploads use presigned S3 URLs (backend never proxies file bytes) | Network trace confirms direct-to-S3 | |
| ☐ | Celery tasks run in < 5 seconds for normal workloads | Task runtime in Celery logs | |

## 8.5 Final Deployment Checklist

| | Test / Task | Expected Result | Status |
|---|---|---|---|
| ☐ | `README.md` documents: local setup, make commands, env vars, test commands | README reviewed | |
| ☐ | All DB migrations committed; no pending unmigrated models | `makemigrations --check` exits 0 | |
| ☐ | `seed_groups` management command documented in README; idempotent | Re-run produces no errors | |
| ☐ | `docker-compose up` (dev) brings system to working state from cold start in < 2 min | Timed cold start | |
| ☐ | Health check endpoint `GET /api/v1/health/` returns `{status: ok, db: ok, redis: ok}` | HTTP 200; all checks ok | |
| ☐ | Sentry or equivalent error tracking configured in production settings | `SENTRY_DSN` set in prod env | |
| ☐ | Logs structured as JSON (use `python-json-logger`) for production log aggregation | LOGGING config uses JSON formatter | |
| ☐ | Database backups documented; `pg_dump` command in Makefile | `make backup` command present | |

---

# 9. Master Phase Gate — Do Not Advance Until All Green

| # | Phase | Key Deliverable | Tests | Gate |
|---|---|---|---|---|
| **1** | **Docker & Scaffolding** | All services up; `make test` exits 0; `.env` documented | 0 (infra) | ☐ PASS |
| **2** | **Auth, RBAC & Audit** | JWT login; group sync signal; AuditLog; PermissionGrant; **Notification model migrated** | **15 AUTH** | ☐ PASS |
| **3** | **Approval Engine** | L1/L2 workflows; routing rules; notifications | **10 APR** | ☐ PASS |
| **4** | **Projects & Site Mgmt** | Project lifecycle; milestones; site reports; requisitions; budget alert task (beat in Ph7) | **15 PROJ** | ☐ PASS |
| **5** | **Shortlets & Bookings** | Properties; clients; bookings; receipts; caution deposits | **13 SHL** | ☐ PASS |
| **6** | **Maintenance** | Request lifecycle; SLA tracking; SLA breach task (beat in Ph7); **Requires Ph4+Ph5** | **12 MNT** | ☐ PASS |
| **7** | **Notifications API + Beat** | All 7 beat tasks registered; in-app notification API; NFY-01–NFY-07 | **7 NFY** (NFY-01 to NFY-07) | ☐ PASS |
| **8** | **Deploy Readiness** | prod compose; security hardening; ≥80% coverage; perf checks | **All** | ☐ PASS |

> **HARD RULE — No Phase Skipping**
> Claude Code must complete and verify each phase before writing code for the next.
> If a checklist item is FAIL: stop, fix the issue, re-run the relevant tests, re-check the item.
> A phase is only PASS when: all its tests are green AND all its checklist items are confirmed.
