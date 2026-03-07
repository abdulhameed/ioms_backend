# CLAUDE CODE — IMPLEMENTATION PRD
## Milestone 1: Core Organizational Management System

> **Stack:** Dockerized Django REST API · PostgreSQL · Redis + Celery  
> **API versioning:** `/api/v1/**` · **HTTP Methods:** GET / POST / PUT / DELETE  
> **Workflow:** Build · Test · Check · Proceed

---

## 0. How to Use This Document

This PRD is structured as a sequential build-test-check workflow. Claude Code works through one phase at a time. Each phase ends with a mandatory checklist. **Do not proceed to the next phase until every checkbox in the current phase is marked PASSED.**

> **Workflow Rule**  
> Phase N code → Phase N tests run → Phase N checklist reviewed → ALL items green → proceed to Phase N+1.  
> If any checklist item fails: fix → re-run tests → re-check before advancing.  
> **Never skip a phase or merge incomplete work forward.**

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
│   │   │   ├── base.py
│   │   │   ├── development.py
│   │   │   └── production.py
│   │   ├── urls.py               # root: /api/v1/ prefix
│   │   ├── wsgi.py
│   │   └── asgi.py
│   ├── apps/
│   │   ├── users/                # Auth, RBAC, Audit
│   │   ├── approvals/            # Workflow engine
│   │   ├── projects/             # Projects, Milestones, Reports, Reqs
│   │   ├── assets/               # Asset Registry, NairaBnB, Bookings, Inventory, Deposits
│   │   ├── maintenance/          # Maintenance requests
│   │   ├── notifications/        # Notification model + Celery tasks
│   │   └── core/                 # Shared models, mixins, utils
│   └── tests/
│       ├── conftest.py
│       ├── test_auth.py
│       ├── test_projects.py
│       ├── test_assets.py
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

## 2.1 Models to Implement

| Model | Key Fields | Notes |
|---|---|---|
| `CustomUser` | id(UUID), full_name, email(unique), phone(unique), role, department, permission_level, is_active, mfa_enabled, mfa_secret(encrypted), created_by, last_login_ip | Extends AbstractUser; email = USERNAME_FIELD |
| `EmailVerificationToken` | id(UUID), user(FK), token(64-char), expires_at, used_at(nullable) | Invalidated after first use OR expiry |
| `PermissionGrant` | id(UUID), user(FK), permission(FK auth.Permission), granted_by(FK), granted_at, is_active, revoked_by(FK nullable), revoked_at | Audit trail of individual permission overrides |
| `AuditLog` | id(UUID), user(FK nullable), role_snapshot, action, resource_type, resource_id, description, metadata(JSON), ip_address, timestamp | APPEND-ONLY. No update/delete at app layer |

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
| ☐ | All 4 models migrated successfully (CustomUser, VerificationToken, PermissionGrant, AuditLog) | Migration exit 0 | |
| ☐ | `seed_groups` creates 13 groups; idempotent on re-run | 13 groups; no duplicates on 2nd run | |
| ☐ | `POST /api/v1/auth/register/` creates inactive user + queues email task | HTTP 201; Celery task visible | |
| ☐ | Email verification activates user and invalidates token | HTTP 200; `is_active=True`; `token.used_at` set | |
| ☐ | JWT login returns access + refresh tokens | HTTP 200; both tokens present | |
| ☐ | Protected routes reject missing/invalid JWT with 401 | HTTP 401 on all tested endpoints | |
| ☐ | Role change immediately updates group membership (no restart needed) | Group confirmed via `/users/{id}/permissions/` | |
| ☐ | PermissionGrant: manager can grant; non-manager cannot; cross-dept blocked | AUTH-10, AUTH-11 passing | |
| ☐ | Promotion clears individual grants | AUTH-09 passing | |
| ☐ | AuditLog written for: login, user_create, role_change, permission_grant | Rows visible in `/api/v1/audit-logs/` | |
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
| `caution_refund` | `hr_full` | `md` | deduction > ₦20,000 OR `is_disputed=True` |

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
| ☐ | Pending > 24h reminder task exists in Celery beat config | Task registered in beat schedule | |
| ☐ | All 10 APR tests passing | `pytest -m phase3` → 10 passed, 0 failed | |
| ☐ | `GET /approvals/` response time < 300ms with 100 workflows in DB | django-silk or logs confirm | |

---

# Phase 4 — Project & Site Management

> *App: `apps/projects/` · Estimated effort: 4 days · Dependency: Phase 3 complete*

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

- `check_budget_alerts` runs hourly; scans all active `ProjectBudgetLine` records.
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
| ☐ | All 15 PROJ tests passing | `pytest -m phase4` → 15 passed, 0 failed | |
| ☐ | `GET /projects/` with 50 projects responds in < 500ms | Response time logged | |

---

# Phase 5 — Asset & Property Management

> *App: `apps/assets/` · Estimated effort: 5 days · Dependency: Phase 3 complete*  
> *Replaces the original shortlets-only scope. Now covers three asset categories, NairaBnB integration, full inventory management, and an enhanced deposit workflow.*

---

## 5.1 Models to Implement

### 5.1.1 Asset Models

| Model | Critical Fields | Auto-logic |
|---|---|---|
| `ShortletApartment` | id, asset_code(auto `SL-NNN`), name, unit_type(`studio\|1_bed\|2_bed\|3_bed\|4_bed\|penthouse\|villa`), location, description(1000), status(`active\|under_maintenance\|retired\|offline`), booking_status(`available\|booked\|occupied\|blocked`), rate_nightly, rate_weekly, rate_monthly, caution_deposit_amount, max_guests, min_stay_nights, max_stay_nights, amenities(JSONField), nairabNb_property_id(nullable), assigned_to(FK), photos(up to 20, 40MB), created_by(FK) | `booking_status` auto-set to `booked` when request accepted, `occupied` on check-in, `available` on check-out |
| `YearlyRentalApartment` | id, asset_code(auto `YR-NNN`), name, unit_type(`studio\|1_bed\|2_bed\|3_bed\|4_bed\|penthouse\|duplex`), location, description(1000), status, lease_status(`available\|leased\|renewal_pending\|terminated`), annual_rent, semi_annual_rate(nullable), quarterly_rate(nullable), service_charge_annual, agreement_fee, caution_deposit_amount, amenities(JSONField), current_tenant(FK Client nullable), lease_start(nullable), lease_end(nullable), rent_due_date(nullable), assigned_to(FK), photos, created_by(FK) | `lease_status` updated manually by Admin; `current_tenant` linked on lease creation |
| `OfficeItem` | id, asset_code(auto `OFF-NNN`), name, item_category(`furniture\|electronics\|appliances\|equipment\|other`), location, quantity, serial_number(nullable), purchase_date(nullable), department(`hr\|finance\|admin\|projects\|marketing\|it`), condition(`new\|good\|fair\|needs_repair`), status, description, photos, assigned_to(FK), created_by(FK) | No booking or inventory system; tracked for maintenance only |

> **Asset Code Sequences:** Use three independent DB sequences — one per asset type. Never use `COUNT()+1`.

### 5.1.2 Inventory Models

| Model | Critical Fields | Auto-logic |
|---|---|---|
| `InventoryTemplate` | id, name, property_type(matches unit_type), items(JSONField array of `{name, category, quantity, condition}`), created_by(FK) | Templates auto-populate `InventoryItem` rows when a new shortlet or yearly rental is saved |
| `InventoryItem` | id, asset_content_type(FK ContentType), asset_object_id(UUID), name, category(`furniture\|appliances\|electronics\|fixtures\|linens\|kitchenware\|other`), quantity, condition(`new\|good\|fair\|worn\|damaged`), notes(200), photos, created_by(FK) | Generic FK allows items to belong to ShortletApartment or YearlyRentalApartment |
| `InventoryVerification` | id, booking(FK Booking), verified_by(FK CustomUser), overall_condition(`excellent\|good\|fair\|poor`), cleaning_fee(Decimal default 0), cleaning_type(`none\|standard\|deep`), additional_charges(Decimal default 0), additional_charge_notes, pdf_file(S3 key nullable), created_at(auto) | Created on checkout completion; immutable after creation |
| `InventoryVerificationItem` | id, verification(FK), inventory_item(FK InventoryItem), status(`present_good\|damaged\|missing\|not_applicable`), damage_description(TextField blank), estimated_cost(Decimal default 0), notes(TextField blank), photos(up to 5) | `estimated_cost` only populated for `damaged` or `missing` items |

### 5.1.3 NairaBnB Integration Models

| Model | Critical Fields | Auto-logic |
|---|---|---|
| `NairaBnBBookingRequest` | id, nairabNb_reference(unique e.g. `NBB-REQ-XXXXX`), property(FK ShortletApartment), client_name, client_email, client_phone, check_in_date, check_out_date, num_guests, total_amount, caution_deposit, special_requests, status(`pending_review\|accepted\|declined\|expired`), handled_by(FK nullable), decline_reason(`property_unavailable\|maintenance_scheduled\|client_verification_failed\|other` nullable), decline_notes, expires_at, received_at(auto) | `expires_at = received_at + 24h`; Celery task auto-sets `status=expired` at deadline |

### 5.1.4 Booking & Deposit Models (Updated)

| Model | Critical Fields | Auto-logic |
|---|---|---|
| `Client` | id, client_code(auto `CLT-NNNN`), full_name, email(unique), phone(unique), alt_phone, id_type, id_number, date_of_birth(nullable), address, company, client_type(`individual\|corporate`), client_source(`nairabNb\|direct\|referral\|walk_in\|other`), is_vip, preferences_notes, emergency_contact_name, emergency_contact_phone, created_by(FK) | Auto-created on NairaBnB booking acceptance; duplicate detection on email OR phone |
| `Booking` | id, booking_code(auto `BKG-YYYY-NNNN`), nairabNb_reference(nullable), nairabNb_request(FK NairaBnBBookingRequest nullable), client(FK), property_content_type(FK ContentType), property_object_id(UUID), check_in_date, check_out_date, rate_type, num_guests, special_requests, base_amount(auto), caution_deposit, total_amount(auto), booking_source(`nairabNb\|direct\|walk_in`), payment_status(`paid_via_nairabNb\|pending\|partial`), status(`confirmed\|checked_in\|checked_out\|completed\|cancelled`), checked_in_at, checked_out_at, check_in_notes, cancellation_initiated_by(`client\|company` nullable), cancellation_reason, cancellation_fee(nullable), created_by(FK) | Generic FK on property allows linking to ShortletApartment or YearlyRentalApartment |
| `BookingReceipt` | id, booking(OneToOne), receipt_number(auto `RCP-YYYY-NNNN`), pdf_file(S3 key), generated_at, generated_by(FK) | Generated async via Celery after booking confirmed; immutable |
| `CautionDeposit` | id, booking(OneToOne), deposit_amount, deduction_amount(default 0), deduction_breakdown(JSONField — itemised list from InventoryVerificationItem), linked_maintenance_requests(M2M MaintenanceRequest), refund_amount(auto), refund_method, account_number(encrypted), account_name, bank_name, is_disputed(BooleanField default False), dispute_notes, status(`held\|pending_refund\|approved_for_refund\|refunded\|partially_deducted\|fully_deducted`), initiated_by(FK), processed_by(FK nullable) | Auto-created on booking with `status=held`; `requires_l2` determined by deduction amount and `is_disputed` flag |

---

## 5.2 NairaBnB Integration — API Endpoints

| Method | URL | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/webhooks/nairabNb/` | Public + HMAC sig | Receive booking request from NairaBnB; creates `NairaBnBBookingRequest`; notifies Front Desk |
| GET | `/api/v1/booking-requests/` | `admin\|front_desk` | List requests; filter by status, property, date |
| GET | `/api/v1/booking-requests/{id}/` | `admin\|front_desk` | Full request detail including property availability check |
| POST | `/api/v1/booking-requests/{id}/accept/` | `admin\|front_desk` | Creates `Booking` + `CautionDeposit` + `Client` (if new); blocks calendar; syncs to NairaBnB |
| POST | `/api/v1/booking-requests/{id}/decline/` | `admin\|front_desk` | Body: `{reason, notes}`; syncs decline to NairaBnB |

> **Webhook Security:** Verify `X-NairaBnB-Signature` HMAC-SHA256 header against `NAIRABAB_WEBHOOK_SECRET` env var. Return HTTP 401 if invalid. Add `NAIRABAB_WEBHOOK_SECRET` to `.env.example`.

> **NairaBnB Sync:** All accept/decline/cancel actions must call the NairaBnB API to sync status. In tests, mock this external call. The sync call must be async (Celery task) — never block the API response waiting for it.

---

## 5.3 Asset Registry — API Endpoints

| Method | URL | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/assets/shortlets/` | authenticated | Filter: status, booking_status, unit_type, location |
| POST | `/api/v1/assets/shortlets/` | `admin` | Creates property; if `unit_type` matches template, auto-populates inventory |
| GET | `/api/v1/assets/shortlets/{id}/` | authenticated | Includes inventory list, booking history, maintenance history |
| PUT | `/api/v1/assets/shortlets/{id}/` | `admin\|front_desk` | |
| GET | `/api/v1/assets/shortlets/{id}/availability/` | authenticated | Returns blocked date ranges for calendar |
| GET | `/api/v1/assets/shortlets/{id}/calendar/` | `admin\|front_desk` | Full calendar view data (monthly/weekly/daily) with colour-coded statuses |
| GET | `/api/v1/assets/shortlets/{id}/inventory/` | `admin\|front_desk` | List all inventory items |
| POST | `/api/v1/assets/shortlets/{id}/inventory/` | `admin` | Add inventory item |
| PUT | `/api/v1/assets/shortlets/{id}/inventory/{iid}/` | `admin` | Update item |
| GET | `/api/v1/assets/yearly/` | authenticated | Filter: lease_status, unit_type, location |
| POST | `/api/v1/assets/yearly/` | `admin` | Creates yearly rental; auto-populates inventory from template |
| GET | `/api/v1/assets/yearly/{id}/` | authenticated | |
| PUT | `/api/v1/assets/yearly/{id}/` | `admin` | |
| GET | `/api/v1/assets/office/` | authenticated | Filter: item_category, department, condition |
| POST | `/api/v1/assets/office/` | `admin` | |
| GET | `/api/v1/assets/office/{id}/` | authenticated | |
| PUT | `/api/v1/assets/office/{id}/` | `admin` | |
| GET | `/api/v1/assets/inventory-templates/` | `admin` | |
| POST | `/api/v1/assets/inventory-templates/` | `admin` | |
| PUT | `/api/v1/assets/inventory-templates/{id}/` | `admin` | |

---

## 5.4 Client Records — API Endpoints

| Method | URL | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/clients/` | `admin\|front_desk` | Search by name, email, phone (icontains); filter by type, source, VIP, activity |
| POST | `/api/v1/clients/` | `admin\|front_desk` | Runs duplicate check; returns 409 if match found |
| GET | `/api/v1/clients/{id}/` | `admin\|front_desk` | Full profile: bookings, payments, deposits, notes, documents |
| PUT | `/api/v1/clients/{id}/` | `admin\|front_desk` | |
| DELETE | `/api/v1/clients/{id}/` | `admin_full` | Soft delete / anonymise for GDPR compliance |
| POST | `/api/v1/clients/{id}/merge/` | `admin_full` | Body: `{merge_into_id}`; merges duplicate records |
| POST | `/api/v1/clients/{id}/notes/` | `admin\|front_desk` | Add timestamped interaction note |
| GET | `/api/v1/clients/export/` | `md\|admin_full` | CSV; excludes `id_number` and `date_of_birth` |

---

## 5.5 Bookings & Check-In/Out — API Endpoints

| Method | URL | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/bookings/` | `admin\|front_desk\|md\|hr_full` | Filter: status, source, date_range, property |
| GET | `/api/v1/bookings/{id}/` | `admin\|front_desk\|md` | Full booking detail |
| POST | `/api/v1/bookings/{id}/check-in/` | `admin\|front_desk` | Sets `status=checked_in`, logs timestamp, prompts ID verification |
| GET | `/api/v1/bookings/{id}/inventory-checklist/` | `admin\|front_desk` | Returns property inventory items pre-loaded for verification |
| POST | `/api/v1/bookings/{id}/complete-checkout/` | `admin\|front_desk` | Submits full `InventoryVerification`; auto-creates maintenance requests for damages; triggers `CautionDeposit` refund workflow |
| GET | `/api/v1/bookings/{id}/checkout-report/pdf/` | `admin\|front_desk` | Returns the generated checkout PDF |
| GET | `/api/v1/bookings/{id}/receipt/` | `admin\|front_desk` | Booking confirmation receipt PDF |
| POST | `/api/v1/bookings/{id}/cancel/` | `admin\|front_desk` | Body: `{initiated_by, reason, notes}`; syncs to NairaBnB; restores property availability |

---

## 5.6 Caution Deposits — API Endpoints

| Method | URL | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/deposits/` | `admin\|hr_full\|md` | Filter: status, property, date |
| GET | `/api/v1/deposits/{id}/` | `admin\|hr_full\|md` | Full detail with deduction breakdown and linked maintenance |
| PUT | `/api/v1/deposits/{id}/` | `admin` | Set refund method + bank details; triggers `ApprovalWorkflow` |
| POST | `/api/v1/deposits/{id}/dispute/` | `admin\|front_desk` | Body: `{dispute_notes}`; sets `is_disputed=True`; escalates to L2 |

> **Deposit L2 Routing Logic (implemented in service layer):**
> ```python
> requires_l2 = (deposit.deduction_amount > 20000) or deposit.is_disputed
> ```

---

## 5.7 Celery Tasks (New in Phase 5)

| Task | Schedule | Description |
|---|---|---|
| `expire_pending_booking_requests` | Every 30 min | Query `NairaBnBBookingRequest` where `expires_at < now()` and `status=pending_review`; set `status=expired`; sync to NairaBnB; notify Front Desk |
| `sync_nairabNb_availability` | Every 15 min | Push current blocked dates for all active shortlets to NairaBnB API |

---

## 5.8 Receipt PDF Fields

- **Header:** Company logo, company name, address, receipt number, date
- **Client:** Full name, phone, email, ID type
- **Property:** Name, type, location, asset code, NairaBnB reference (if applicable)
- **Booking:** Check-in date, check-out date, duration, rate type, booking source
- **Charges:** Base amount breakdown, caution deposit, total paid
- **Payment:** Method/source (NairaBnB / Direct), reference number, payment date
- **Footer:** "Thank you" note, QR code linking to booking reference

---

## 5.9 Phase 5 Tests

| Test ID | Test Description | Assertion |
|---|---|---|
| SHL-01 | Create ShortletApartment → code `SL-NNN`; YearlyRental → `YR-NNN`; OfficeItem → `OFF-NNN` | HTTP 201; all 3 codes match their regexes |
| SHL-02 | Create shortlet with matching template → inventory auto-populated | InventoryItem rows created from template |
| SHL-03 | NairaBnB webhook with valid HMAC → `NairaBnBBookingRequest` created; Front Desk notified | HTTP 200; request in DB; notification created |
| SHL-04 | NairaBnB webhook with invalid HMAC → rejected | HTTP 401 |
| SHL-05 | Accept booking request → `Booking` + `CautionDeposit` + `Client` created; NairaBnB sync called (mocked) | All 3 rows created; mock called |
| SHL-06 | Accept request for already-blocked dates → 409 | HTTP 409 |
| SHL-07 | Decline request with reason → `status=declined`; NairaBnB sync called | HTTP 200; mock called |
| SHL-08 | Booking request not actioned within 24h → Celery task sets `status=expired` | `status=expired` after task run |
| SHL-09 | Cancel confirmed booking → `status=cancelled`; property `booking_status=available`; NairaBnB synced | HTTP 200; property available |
| SHL-10 | Check-in → `status=checked_in`; `checked_in_at` set; property `booking_status=occupied` | HTTP 200; timestamps set |
| SHL-11 | `GET /bookings/{id}/inventory-checklist/` → returns all property inventory items | HTTP 200; item count matches InventoryItem count |
| SHL-12 | Submit checkout with 2 damaged items → `InventoryVerification` created; 2 maintenance requests auto-created linked to booking | HTTP 200; 2 MNT rows with `booking` FK |
| SHL-13 | Checkout deduction ≤ ₦20K → `CautionDeposit` approval `requires_l2=False` | Workflow `requires_l2=False` |
| SHL-14 | Checkout deduction > ₦20K → `CautionDeposit` approval `requires_l2=True` | Workflow `requires_l2=True` |
| SHL-15 | `is_disputed=True` on small deduction → `requires_l2=True` regardless | Workflow `requires_l2=True` |
| SHL-16 | Checkout PDF report generated with damage photos and itemised cost breakdown | `Content-Type: application/pdf`; PDF contains item names |
| SHL-17 | Create client → `CLT-NNNN`; duplicate phone returns 409 | HTTP 201; 409 on duplicate |
| SHL-18 | Client auto-created on NairaBnB booking acceptance; not duplicated on second booking | 1 client row after 2 bookings from same email |
| SHL-19 | Client export CSV excludes `id_number` and `date_of_birth` | CSV missing both columns |
| SHL-20 | `front_desk` cannot access `DELETE /clients/{id}/` | HTTP 403 |

---

## 5.10 Phase 5 Checklist

| | Test / Task | Expected Result | Status |
|---|---|---|---|
| ☐ | All models migrated: ShortletApartment, YearlyRentalApartment, OfficeItem, InventoryTemplate, InventoryItem, InventoryVerification, InventoryVerificationItem, NairaBnBBookingRequest, Client, Booking (updated), BookingReceipt, CautionDeposit (updated) | Migration exit 0; no conflicts |  |
| ☐ | Three asset code sequences work independently; no duplicates under concurrent creation | SHL-01 passing; no collision |  |
| ☐ | Inventory template auto-populates on new shortlet/yearly property creation | SHL-02 passing |  |
| ☐ | NairaBnB webhook validates HMAC; rejects invalid signatures | SHL-03, SHL-04 passing |  |
| ☐ | Booking acceptance creates Booking + CautionDeposit + Client atomically (DB transaction) | SHL-05 passing; no partial rows if any step fails |  |
| ☐ | Double-booking via accept endpoint blocked (availability check inside transaction) | SHL-06 passing |  |
| ☐ | 24h auto-expire Celery task sets `status=expired` without re-processing already-expired requests | SHL-08 passing; no duplicate syncs |  |
| ☐ | Checkout inventory verification creates `InventoryVerification` and auto-creates maintenance requests for all damaged/missing items | SHL-12 passing |  |
| ☐ | Deposit L2 routing: >₦20K deduction OR `is_disputed=True` → `requires_l2=True`; ≤₦20K clean → `requires_l2=False` | SHL-13, SHL-14, SHL-15 passing |  |
| ☐ | `deduction_breakdown` JSONField contains itemised list from `InventoryVerificationItem` | Breakdown matches verification items |  |
| ☐ | Checkout report PDF generated with damage photos and cost breakdown | SHL-16 passing |  |
| ☐ | NairaBnB sync calls (accept, decline, cancel) are async Celery tasks; API response does not wait for them | API response < 200ms; sync visible in Celery logs |  |
| ☐ | `account_number` stored encrypted in DB | Raw DB value is ciphertext |  |
| ☐ | Client merge endpoint deduplicates records; booking history transferred to surviving record | Merged client has combined history |  |
| ☐ | Client export CSV excludes `id_number` and `date_of_birth` | SHL-19 passing |  |
| ☐ | All 20 SHL tests passing | `pytest -m phase5` → 20 passed, 0 failed |  |
| ☐ | `NAIRABAB_WEBHOOK_SECRET` added to `.env.example`; not hardcoded anywhere | `git grep` finds no hardcoded secret |  |

---

# Phase 6 — Maintenance & Issue Escalation

> *App: `apps/maintenance/` · Estimated effort: 2 days · Dependency: Phase 5 complete*

## 6.1 Models to Implement

| Model | Critical Fields | Auto-logic |
|---|---|---|
| `MaintenanceRequest` | id, request_code(auto `MNT-YYYY-NNNN`), issue_type, location_type, property(FK null), project(FK null), location_details, priority, description(1000), status, reported_by(FK), assigned_to(FK null), assigned_by(FK null), assignment_notes, expected_resolution_at, resolved_at, closed_at, closed_by(FK null), resolution_notes, labor_hours, parts_cost, sla_deadline(auto), is_overdue(default False) | `sla_deadline = reported_at + SLA duration by priority`; `is_overdue` set by Celery beat task |
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

- Runs every **30 minutes** via Celery beat.
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
| ☐ | All 3 models migrated; status updates append-only (no update/delete on `MaintenanceStatusUpdate`) | Migration exit 0; 405 on `PUT /status-updates/{id}/` | |
| ☐ | `sla_deadline` auto-calculated correctly for all 4 priority levels | MNT-01, MNT-02 passing | |
| ☐ | Decline flow returns request to open and notifies admin | MNT-05 passing | |
| ☐ | Celery SLA breach task sets `is_overdue` without duplicating alerts | MNT-09, MNT-10 passing | |
| ☐ | Photo upload enforces 10-file and 20MB limits | MNT-12 passing | |
| ☐ | Metrics endpoint returns correct aggregates | MNT-11 passing | |
| ☐ | All 12 MNT tests passing | `pytest -m phase6` → 12 passed, 0 failed | |

---

# Phase 7 — Notifications & Background Jobs

> *App: `apps/notifications/` · Estimated effort: 1.5 days · Dependency: Phase 6 complete*

## 7.1 Notification Model

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `recipient` | FK(CustomUser) | |
| `notification_type` | CharField choices | `approval_pending \| approval_decided \| assignment \| sla_warning \| budget_alert \| booking_reminder \| system` |
| `title` | CharField(200) | |
| `body` | TextField | |
| `resource_type` | CharField(50) blank | e.g. `Project`, `Booking`, `MaintenanceRequest` |
| `resource_id` | UUID nullable | For deep-link navigation in frontend |
| `channel` | CharField choices | `in_app \| email \| sms` |
| `is_read` | BooleanField default False | |
| `read_at` | DateTimeField nullable | |
| `created_at` | DateTimeField auto | |

## 7.2 Celery Beat Schedule

| Task Name | Schedule | Description |
|---|---|---|
| `expire_pending_booking_requests` | Every 30 min | Auto-decline NairaBnB booking requests not actioned within 24h; sync to NairaBnB |
| `sync_nairabNb_availability` | Every 15 min | Push current blocked dates for all active shortlets to NairaBnB API |
| `check_sla_breaches` | Every 30 min | Flag overdue maintenance; send alerts |
| `check_budget_alerts` | Every 1 hour | Detect 80%/95% utilization; send once per threshold crossing |
| `booking_checkin_reminder` | Daily 8:00 AM | Notify Front Desk of tomorrow's check-ins |
| `project_deadline_alert` | Daily 9:00 AM | Notify PM + MD of projects due within 7 days |
| `pending_approval_reminder` | Every 4 hours | Remind approvers of items pending > 24h |
| `dashboard_cache_refresh` | Every 60 seconds | Rebuild Redis cache keys for dashboard KPIs |
| `audit_log_archive` | Monthly (1st, 3:00 AM) | Archive audit logs older than 7 years to cold storage |

## 7.3 In-App Notification API Endpoints

| Method | URL | Description |
|---|---|---|
| GET | `/api/v1/notifications/` | List my notifications; filter by `is_read`, type; paginated |
| POST | `/api/v1/notifications/{id}/read/` | Mark single notification as read |
| POST | `/api/v1/notifications/read-all/` | Mark all my notifications as read |
| GET | `/api/v1/notifications/unread-count/` | Returns `{count: N}` for UI badge |

## 7.4 Phase 7 Checklist

| | Test / Task | Expected Result | Status |
|---|---|---|---|
| ☐ | Notification model migrated | Migration exit 0 | |
| ☐ | All 9 Celery beat tasks registered in beat schedule; visible in Celery inspect | `celery inspect scheduled` shows all 9 | |
| ☐ | Celery worker processes tasks without crashing (run each task manually once) | No exceptions in Celery logs | |
| ☐ | In-app notification API returns only current user's notifications | `GET /notifications/` filtered by recipient | |
| ☐ | Unread count updates after mark-read | Count decrements correctly | |
| ☐ | Email notifications sent for: user_created, approval_decided, sla_warning (test with console backend) | Email content visible in console | |
| ☐ | All notification tasks are async (never block API response) | API response < 200ms even when email is slow | |

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
| **2** | **Auth, RBAC & Audit** | JWT login; group sync signal; AuditLog; PermissionGrant | **15 AUTH** | ☐ PASS |
| **3** | **Approval Engine** | L1/L2 workflows; routing rules; notifications | **10 APR** | ☐ PASS |
| **4** | **Projects & Site Mgmt** | Project lifecycle; milestones; site reports; requisitions; budget alerts | **15 PROJ** | ☐ PASS |
| **5** | **Asset & Property Management** | Three asset types (shortlet, yearly, office); NairaBnB integration; inventory verification; enhanced deposit workflow | **20 SHL** | ☐ PASS |
| **6** | **Maintenance** | Request lifecycle; SLA tracking; Celery overdue task | **12 MNT** | ☐ PASS |
| **7** | **Notifications & Celery** | All 9 beat tasks; in-app API; async email | **7 NFY** | ☐ PASS |
| **8** | **Deploy Readiness** | prod compose; security hardening; ≥80% coverage; perf checks | **All** | ☐ PASS |

> **HARD RULE — No Phase Skipping**  
> Claude Code must complete and verify each phase before writing code for the next.  
> If a checklist item is FAIL: stop, fix the issue, re-run the relevant tests, re-check the item.  
> A phase is only PASS when: all its tests are green AND all its checklist items are confirmed.  
> This sequential approach prevents cascading bugs and ensures each layer is solid before building on it.
