# IOMS API Testing Guide

> **Base URL:** `http://localhost:8000/api/v1`
> **Auth header:** `Authorization: Bearer <access_token>`
> **Content-Type:** `application/json` (all requests)
> **IDs:** UUID4 format
> **Money fields:** Decimal string, e.g. `"125000.00"`

---

## Interactive API Docs (Swagger / ReDoc)

The live OpenAPI 3 schema is auto-generated from the codebase and available at:

| URL | Description |
|---|---|
| `http://localhost:8000/api/schema/` | Raw OpenAPI 3 YAML download |
| `http://localhost:8000/api/schema/swagger-ui/` | Swagger UI — interactive, try-it-out |
| `http://localhost:8000/api/schema/redoc/` | ReDoc — clean readable reference |

> The Swagger UI supports **Authorize** — paste your `Bearer <access_token>` there to authenticate all requests directly from the browser.

---

## Phase Status

| Phase | Status | Endpoints |
|---|---|---|
| Phase 1 — Infrastructure | ✅ Complete | `/`, `/health/` |
| Phase 2 — Auth & RBAC | ✅ Complete | `/auth/**`, `/users/**`, `/audit-logs/**` |
| Phase 3 — Approvals | ✅ Complete | `/approvals/**` |
| Phase 4 — Projects | ✅ Complete | `/projects/**` |
| Phase 5 — Shortlets | ✅ Complete | `/properties/**`, `/clients/**`, `/bookings/**`, `/deposits/**` |
| Phase 6 — Maintenance | ✅ Complete | `/maintenance/**` |
| Phase 7 — Notifications API | ✅ Complete | `/notifications/**` |

---

## Prerequisites — First-Time Setup

These steps are required once on a fresh database before any authenticated endpoint can be tested.

### Step 1 — Start the stack

```bash
make up
make migrate
make seed      # creates all 13 Django groups (idempotent)
```

### Step 2 — Create the first privileged user

There is no public signup. Run the seed command to create the default `md` admin user:

```bash
make seed-admin
```

This creates `admin@example.com` / `AdminPass123!` with `role=md` and full system access. The command is idempotent — it skips silently if the user already exists.

To use different credentials or create an `hr_full` user instead:

```bash
docker-compose exec backend python manage.py create_admin_user \
  --email boss@example.com --password Secret99! --role hr_full
```

**Note:** MFA defaults to `False`, so login returns a full JWT immediately without an MFA challenge.

### Step 3 — Login to get a token

```http
POST /api/v1/auth/login/
Content-Type: application/json

{
  "email": "admin@example.com",
  "password": "AdminPass123!"
}
```

The response contains `access` and `refresh` tokens. Copy the `access` value and use it as the `Authorization: Bearer <access_token>` header in all authenticated requests throughout this guide.

---

## Phase 1 — Infrastructure

### GET /api/v1/

```http
GET /api/v1/ HTTP/1.1
```

**Expected response (200):**
```json
{
  "api": "IOMS",
  "version": "v1",
  "status": "operational"
}
```

---

### GET /api/v1/health/

```http
GET /api/v1/health/ HTTP/1.1
```

**Expected response (200):**
```json
{
  "status": "ok",
  "db": "ok",
  "redis": "ok"
}
```

---

## Phase 2 — Authentication & RBAC

### POST /api/v1/auth/register/

> **Auth required:** Login first (`POST /auth/login/`) as an `hr_full` or `md` user to get a token, then pass it in the `Authorization` header. This endpoint is not public.

Creates an inactive user and queues a verification email.

```http
POST /api/v1/auth/register/ HTTP/1.1
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "email": "jane.doe@example.com",
  "full_name": "Jane Doe",
  "phone": "+2348012345678",
  "role": "pm_full",
  "department": "Projects",
  "permission_level": "limited"
}
```

**Expected response (201):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "jane.doe@example.com",
  "full_name": "Jane Doe",
  "phone": "+2348012345678",
  "role": "pm_full",
  "department": "Projects",
  "permission_level": "limited",
  "is_active": false
}
```

**Error — duplicate email (400):**
```json
{
  "email": ["A user with this email already exists."]
}
```

**Error — insufficient permission (403):**
```json
{
  "error": "permission_denied",
  "message": "You do not have permission to perform this action."
}
```

---

### POST /api/v1/auth/verify-email/

Activates the user account using the token sent via email.

```http
POST /api/v1/auth/verify-email/ HTTP/1.1
Content-Type: application/json

{
  "token": "abc123def456..."
}
```

**Expected response (200):**
```json
{
  "detail": "Email verified. Account activated."
}
```

**Error — expired or invalid token (400):**
```json
{
  "token": ["Token has expired or already been used."]
}
```

---

### POST /api/v1/auth/set-password/

First-time password setup using the verification token.

```http
POST /api/v1/auth/set-password/ HTTP/1.1
Content-Type: application/json

{
  "token": "abc123def456...",
  "password": "SecurePass123!"
}
```

**Expected response (200):**
```json
{
  "detail": "Password set. Account activated."
}
```

---

### POST /api/v1/auth/login/

Returns a JWT access + refresh pair. Writes an AuditLog entry.

```http
POST /api/v1/auth/login/ HTTP/1.1
Content-Type: application/json

{
  "email": "jane.doe@example.com",
  "password": "SecurePass123!"
}
```

**Expected response (200):**
```json
{
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

> If MFA is required for the role (`md`, `hr_full`), a partial token is returned and MFA verification must be completed before the full JWT is issued.

**Error — invalid credentials (401):**
```json
{
  "password": ["Invalid credentials."]
}
```

**Error — account locked after 5 failures (423):**
```json
{
  "non_field_errors": ["account_locked"]
}
```

**Error — rate limit exceeded (429):**
```json
{
  "detail": "Request was throttled."
}
```

---

### POST /api/v1/auth/token/refresh/

```http
POST /api/v1/auth/token/refresh/ HTTP/1.1
Content-Type: application/json

{
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Expected response (200):**
```json
{
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

---

### POST /api/v1/auth/logout/

Blacklists the refresh token.

```http
POST /api/v1/auth/logout/ HTTP/1.1
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Expected response (204):** *(no body)*

---

### POST /api/v1/auth/mfa/setup/

Returns TOTP provisioning URI for authenticator app setup.

```http
POST /api/v1/auth/mfa/setup/ HTTP/1.1
Authorization: Bearer <access_token>
```

**Expected response (200):**
```json
{
  "provisioning_uri": "otpauth://totp/IOMS:jane.doe@example.com?secret=BASE32SECRET&issuer=IOMS",
  "secret": "BASE32SECRET"
}
```

---

### POST /api/v1/auth/mfa/verify/

Completes MFA login; returns full JWT pair.

```http
POST /api/v1/auth/mfa/verify/ HTTP/1.1
Authorization: Bearer <partial_access_token>
Content-Type: application/json

{
  "code": "123456"
}
```

**Expected response (200):**
```json
{
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Error — invalid TOTP code (400):**
```json
{
  "code": ["Invalid or expired MFA code."]
}
```

---

### GET /api/v1/users/

Requires `can_manage_users`. Supports filtering by `role`, `department`, `is_active`.

```http
GET /api/v1/users/?role=pm_full&is_active=true HTTP/1.1
Authorization: Bearer <access_token>
```

**Expected response (200):**
```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "email": "jane.doe@example.com",
      "full_name": "Jane Doe",
      "phone": "+2348012345678",
      "role": "pm_full",
      "department": "Projects",
      "permission_level": "limited",
      "is_active": true,
      "mfa_enabled": false,
      "date_joined": "2026-03-05T14:30:00Z"
    }
  ]
}
```

---

### GET /api/v1/users/me/

Returns the authenticated user's profile.

```http
GET /api/v1/users/me/ HTTP/1.1
Authorization: Bearer <access_token>
```

**Expected response (200):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "jane.doe@example.com",
  "full_name": "Jane Doe",
  "phone": "+2348012345678",
  "username": "jane.doe@example.com",
  "role": "pm_full",
  "department": "Projects",
  "permission_level": "limited",
  "is_active": true,
  "mfa_enabled": false,
  "last_login_ip": "192.168.1.1",
  "date_joined": "2026-03-05T14:30:00Z",
  "created_by": "880e8400-e29b-41d4-a716-446655440001"
}
```

---

### PUT /api/v1/users/me/

Update own profile (name, phone).

```http
PUT /api/v1/users/me/ HTTP/1.1
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "full_name": "Jane A. Doe",
  "phone": "+2348087654321"
}
```

**Expected response (200):** *(updated user object)*

---

### GET /api/v1/users/{id}/

```http
GET /api/v1/users/550e8400-e29b-41d4-a716-446655440000/ HTTP/1.1
Authorization: Bearer <access_token>
```

**Expected response (200):** *(full user detail object)*

---

### PUT /api/v1/users/{id}/

Manager updates role or department. Role change triggers group sync signal.

```http
PUT /api/v1/users/550e8400-e29b-41d4-a716-446655440000/ HTTP/1.1
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "role": "hr_limited",
  "department": "Human Resources",
  "permission_level": "limited",
  "is_active": true
}
```

**Expected response (200):** *(updated user object)*

---

### GET /api/v1/users/{id}/permissions/

Returns group permissions + individual grants.

```http
GET /api/v1/users/550e8400-e29b-41d4-a716-446655440000/permissions/ HTTP/1.1
Authorization: Bearer <access_token>
```

**Expected response (200):**
```json
{
  "groups": ["pm_full"],
  "individual_grants": [
    {
      "codename": "can_approve_requisition",
      "granted_by": "880e8400-e29b-41d4-a716-446655440001",
      "granted_at": "2026-03-05T14:30:00Z",
      "is_active": true
    }
  ]
}
```

---

### POST /api/v1/users/{id}/grant-permission/

Manager grants an individual permission to a same-department user.

```http
POST /api/v1/users/550e8400-e29b-41d4-a716-446655440000/grant-permission/ HTTP/1.1
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "permission_codename": "can_approve_requisition"
}
```

**Expected response (200):**
```json
{
  "detail": "Permission granted."
}
```

**Error — cross-department (403):**
```json
{
  "error": "permission_denied",
  "message": "You can only grant permissions to users in your department."
}
```

---

### POST /api/v1/users/{id}/revoke-permission/

```http
POST /api/v1/users/550e8400-e29b-41d4-a716-446655440000/revoke-permission/ HTTP/1.1
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "permission_codename": "can_approve_requisition"
}
```

**Expected response (200):**
```json
{
  "detail": "Permission revoked."
}
```

---

### GET /api/v1/audit-logs/

Requires `md` or `hr_full`. Paginated; filterable by `action`.

```http
GET /api/v1/audit-logs/?action=auth.login&limit=20 HTTP/1.1
Authorization: Bearer <access_token>
```

**Expected response (200):**
```json
{
  "count": 5,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "660e8400-e29b-41d4-a716-446655440000",
      "user": "550e8400-e29b-41d4-a716-446655440000",
      "user_email": "jane.doe@example.com",
      "role_snapshot": "pm_full",
      "action": "auth.login",
      "resource_type": "user",
      "resource_id": "550e8400-e29b-41d4-a716-446655440000",
      "description": "User logged in",
      "metadata": {"ip": "192.168.1.1", "device": "Mozilla/5.0", "success": true},
      "ip_address": "192.168.1.1",
      "timestamp": "2026-03-05T14:30:00Z"
    }
  ]
}
```

---

### GET /api/v1/audit-logs/export/

Downloads audit log as CSV. Requires `md` or `hr_full`.

```http
GET /api/v1/audit-logs/export/ HTTP/1.1
Authorization: Bearer <access_token>
```

**Expected response (200):** `Content-Type: text/csv`

---

## Phase 3 — Approval Workflow Engine

> **Status: Pending** — endpoints available after Phase 3 implementation.

### GET /api/v1/approvals/

Lists pending approvals and approvals created by the current user. Filterable by `status`, `workflow_type`.

```http
GET /api/v1/approvals/?status=pending_l1 HTTP/1.1
Authorization: Bearer <access_token>
```

**Expected response (200):**
```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "770e8400-e29b-41d4-a716-446655440000",
      "workflow_type": "project_proposal",
      "status": "pending_l1",
      "initiated_by": "550e8400-e29b-41d4-a716-446655440000",
      "l1_approver": "880e8400-e29b-41d4-a716-446655440001",
      "requires_l2": true,
      "created_at": "2026-03-05T14:30:00Z"
    }
  ]
}
```

---

### GET /api/v1/approvals/{id}/

Full workflow detail with comments. Accessible to participants, `md`, and `hr_full`.

```http
GET /api/v1/approvals/770e8400-e29b-41d4-a716-446655440000/ HTTP/1.1
Authorization: Bearer <access_token>
```

---

### POST /api/v1/approvals/{id}/decide/

Submit an approval decision. Only the assigned approver can call this.

```http
POST /api/v1/approvals/770e8400-e29b-41d4-a716-446655440000/decide/ HTTP/1.1
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "decision": "approved",
  "notes": "All documents reviewed and approved."
}
```

**Reject (notes must be ≥ 20 characters):**
```json
{
  "decision": "rejected",
  "notes": "Budget is too high for current fiscal year constraints."
}
```

**`decision` values:** `approved` | `rejected` | `more_info`

**Error — rejection notes too short (400):**
```json
{
  "notes": ["Rejection notes must be at least 20 characters."]
}
```

---

### POST /api/v1/approvals/{id}/withdraw/

Initiator withdraws. Only allowed when `status` is `pending_l1` or `pending_l2`.

```http
POST /api/v1/approvals/770e8400-e29b-41d4-a716-446655440000/withdraw/ HTTP/1.1
Authorization: Bearer <access_token>
```

**Expected response (200):**
```json
{
  "status": "withdrawn"
}
```

---

### POST /api/v1/approvals/{id}/comment/

Add a comment, info request, or info response.

```http
POST /api/v1/approvals/770e8400-e29b-41d4-a716-446655440000/comment/ HTTP/1.1
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "comment": "Please attach the updated vendor quote.",
  "comment_type": "info_request"
}
```

**`comment_type` values:** `comment` | `info_request` | `info_response`

---

### GET /api/v1/approvals/pending-count/

Returns badge count for dashboard.

```http
GET /api/v1/approvals/pending-count/ HTTP/1.1
Authorization: Bearer <access_token>
```

**Expected response (200):**
```json
{
  "count": 3
}
```

---

## Phase 4 — Projects & Site Management

> **Status: Pending** — endpoints available after Phase 4 implementation.

### POST /api/v1/projects/

Creates a project in `draft` status. `project_code` is null until L2 approval.

```http
POST /api/v1/projects/ HTTP/1.1
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "name": "Lekki Phase 2 Development",
  "project_type": "residential",
  "location_text": "Lekki, Lagos",
  "lat": 6.4281,
  "lng": 3.4219,
  "start_date": "2026-04-01",
  "expected_end_date": "2027-06-30",
  "budget_total": "85000000.00",
  "scope": "Construction of 20 housing units including roads and utilities."
}
```

**Expected response (201):**
```json
{
  "id": "990e8400-e29b-41d4-a716-446655440000",
  "project_code": null,
  "name": "Lekki Phase 2 Development",
  "status": "draft",
  "health": "not_started",
  "progress_pct": 0
}
```

---

### POST /api/v1/projects/{id}/submit/

Submits draft project for approval. Creates an `ApprovalWorkflow`.

```http
POST /api/v1/projects/990e8400-e29b-41d4-a716-446655440000/submit/ HTTP/1.1
Authorization: Bearer <access_token>
```

**Expected response (200):**
```json
{
  "status": "pending_l1",
  "workflow_id": "770e8400-e29b-41d4-a716-446655440000"
}
```

**Error — edit after submission (400):**
```json
{
  "error": "invalid_state",
  "message": "Project cannot be edited after submission."
}
```

---

### GET /api/v1/projects/{id}/budget/

Returns budget breakdown and utilization percentages.

```http
GET /api/v1/projects/990e8400-e29b-41d4-a716-446655440000/budget/ HTTP/1.1
Authorization: Bearer <access_token>
```

**Expected response (200):**
```json
{
  "budget_total": "85000000.00",
  "lines": [
    {
      "category": "Civil Works",
      "allocated_amount": "40000000.00",
      "committed_amount": "5000000.00",
      "spent_amount": "2000000.00",
      "remaining": "33000000.00",
      "utilization_pct": 16.47
    }
  ]
}
```

---

### POST /api/v1/projects/{id}/milestones/

```http
POST /api/v1/projects/990e8400-e29b-41d4-a716-446655440000/milestones/ HTTP/1.1
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "title": "Foundation Complete",
  "target_date": "2026-08-01",
  "depends_on": null
}
```

**Expected response (201):**
```json
{
  "id": "aa0e8400-e29b-41d4-a716-446655440000",
  "title": "Foundation Complete",
  "target_date": "2026-08-01",
  "status": "pending",
  "actual_completion_date": null
}
```

---

### POST /api/v1/projects/{id}/site-reports/

Locked on creation; no edits allowed after submission.

```http
POST /api/v1/projects/990e8400-e29b-41d4-a716-446655440000/site-reports/ HTTP/1.1
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "report_date": "2026-03-05",
  "report_type": "daily",
  "task_description": "Excavation of grid B3-B7",
  "progress_summary": "Excavation 60% complete. No delays encountered.",
  "completion_pct_added": 5,
  "external_labor_count": 12,
  "weather_condition": "sunny",
  "has_safety_incident": false,
  "materials": [
    {
      "material_name": "Sand",
      "opening_balance": 200,
      "new_deliveries": 50,
      "quantity_used": 80,
      "unit": "tonnes",
      "work_area": "B3"
    }
  ]
}
```

**Expected response (201):** *(site report object with `is_locked: true`)*

**Error — quantity_used exceeds available (400):**
```json
{
  "materials": [{"quantity_used": ["Cannot exceed opening balance + new deliveries."]}]
}
```

---

### POST /api/v1/projects/{id}/requisitions/

Creates a payment requisition. Submit separately to trigger approval workflow.

```http
POST /api/v1/projects/990e8400-e29b-41d4-a716-446655440000/requisitions/ HTTP/1.1
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "budget_line": "bb0e8400-e29b-41d4-a716-446655440000",
  "category": "materials",
  "urgency": "normal",
  "description": "Procurement of reinforcement bars for foundation.",
  "payment_structure": "split",
  "mobilization_pct": 60,
  "balance_terms": "On delivery and sign-off",
  "vendor_name": "SteelMax Ltd",
  "line_items": [
    {
      "description": "16mm Reinforcement Bar",
      "quantity": 500,
      "unit_of_measure": "lengths",
      "unit_cost": "3500.00"
    }
  ]
}
```

**Expected response (201):**
```json
{
  "id": "cc0e8400-e29b-41d4-a716-446655440000",
  "req_code": "REQ-2026-0001",
  "total_amount": "1750000.00",
  "status": "draft"
}
```

---

### GET /api/v1/projects/dashboard/

Aggregated KPI cards; cached 60 seconds in Redis. Requires `md` or `pm_full`.

```http
GET /api/v1/projects/dashboard/ HTTP/1.1
Authorization: Bearer <access_token>
```

**Expected response (200):**
```json
{
  "total_projects": 12,
  "by_status": {"planning": 3, "in_progress": 7, "on_hold": 1, "completed": 1},
  "at_risk": 2,
  "budget_utilization_avg_pct": 43.5
}
```

---

### GET /api/v1/projects/{id}/site-reports/{rid}/pdf/

Returns a PDF of the site report.

```http
GET /api/v1/projects/990e8400-e29b-41d4-a716-446655440000/site-reports/dd0e8400-e29b-41d4-a716-446655440000/pdf/ HTTP/1.1
Authorization: Bearer <access_token>
```

**Expected response (200):** `Content-Type: application/pdf`

---

## Phase 5 — Shortlets & Asset Management

> **Status: Pending** — endpoints available after Phase 5 implementation.

### POST /api/v1/properties/

```http
POST /api/v1/properties/ HTTP/1.1
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "name": "Victoria Island Suite A",
  "unit_type": "studio",
  "location": "Plot 5, Ahmadu Bello Way, Victoria Island, Lagos",
  "rate_nightly": "45000.00",
  "rate_weekly": "280000.00",
  "rate_monthly": "900000.00",
  "caution_deposit_amount": "50000.00",
  "amenities": ["wifi", "ac", "parking", "pool"],
  "description": "Modern studio apartment with city views."
}
```

**Expected response (201):**
```json
{
  "id": "ee0e8400-e29b-41d4-a716-446655440000",
  "property_code": "PROP-SL-001",
  "name": "Victoria Island Suite A",
  "status": "available"
}
```

---

### GET /api/v1/properties/{id}/availability/

Returns blocked date ranges for the property.

```http
GET /api/v1/properties/ee0e8400-e29b-41d4-a716-446655440000/availability/ HTTP/1.1
Authorization: Bearer <access_token>
```

**Expected response (200):**
```json
[
  {"check_in": "2026-03-10", "check_out": "2026-03-15"},
  {"check_in": "2026-03-20", "check_out": "2026-03-25"}
]
```

---

### POST /api/v1/clients/

Runs duplicate detection on email and phone. Returns 409 if duplicate found.

```http
POST /api/v1/clients/ HTTP/1.1
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "full_name": "Emeka Okafor",
  "email": "emeka@example.com",
  "phone": "+2348023456789",
  "id_type": "national_id",
  "id_number": "NIN12345678",
  "client_type": "individual",
  "is_vip": false
}
```

**Expected response (201):**
```json
{
  "id": "ff0e8400-e29b-41d4-a716-446655440000",
  "client_code": "CLT-0001",
  "full_name": "Emeka Okafor"
}
```

**Error — duplicate phone (409):**
```json
{
  "error": "duplicate_client",
  "message": "A client with this phone already exists.",
  "existing_id": "ff0e8400-e29b-41d4-a716-446655440000"
}
```

---

### POST /api/v1/bookings/

Checks availability with `SELECT FOR UPDATE`. Auto-creates `CautionDeposit`. Queues receipt PDF generation.

```http
POST /api/v1/bookings/ HTTP/1.1
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "client": "ff0e8400-e29b-41d4-a716-446655440000",
  "property": "ee0e8400-e29b-41d4-a716-446655440000",
  "check_in_date": "2026-04-01",
  "check_out_date": "2026-04-07",
  "rate_type": "weekly",
  "num_guests": 2,
  "payment_method": "bank_transfer",
  "payment_reference": "TRF-20260401-001"
}
```

**Expected response (201):**
```json
{
  "id": "aa1e8400-e29b-41d4-a716-446655440000",
  "booking_code": "BKG-2026-0001",
  "base_amount": "280000.00",
  "caution_deposit": "50000.00",
  "total_amount": "330000.00",
  "status": "confirmed"
}
```

**Error — property unavailable (409):**
```json
{
  "error": "property_unavailable",
  "message": "Property is booked for these dates."
}
```

---

### POST /api/v1/bookings/{id}/check-in/

```http
POST /api/v1/bookings/aa1e8400-e29b-41d4-a716-446655440000/check-in/ HTTP/1.1
Authorization: Bearer <access_token>
```

**Expected response (200):**
```json
{
  "status": "checked_in",
  "checked_in_at": "2026-04-01T10:30:00Z"
}
```

---

### POST /api/v1/bookings/{id}/check-out/

Triggers caution deposit refund workflow automatically.

```http
POST /api/v1/bookings/aa1e8400-e29b-41d4-a716-446655440000/check-out/ HTTP/1.1
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "condition": "good",
  "deduction_amount": "0.00",
  "notes": "Property returned in excellent condition."
}
```

**With deduction:**
```json
{
  "condition": "damaged",
  "deduction_amount": "15000.00",
  "notes": "Broken window in bedroom. Repair cost estimated at NGN 15,000."
}
```

**Expected response (200):**
```json
{
  "status": "checked_out",
  "checked_out_at": "2026-04-07T11:00:00Z",
  "refund_workflow_id": "bb1e8400-e29b-41d4-a716-446655440000"
}
```

---

### GET /api/v1/bookings/{id}/receipt/

Returns booking receipt PDF.

```http
GET /api/v1/bookings/aa1e8400-e29b-41d4-a716-446655440000/receipt/ HTTP/1.1
Authorization: Bearer <access_token>
```

**Expected response (200):** `Content-Type: application/pdf`

**Error — not yet generated (404):**
```json
{
  "error": "not_found",
  "message": "Receipt has not been generated yet."
}
```

---

### PUT /api/v1/deposits/{id}/

Set refund method and bank details. Triggers caution refund approval workflow.

```http
PUT /api/v1/deposits/cc1e8400-e29b-41d4-a716-446655440000/ HTTP/1.1
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "refund_method": "bank_transfer",
  "account_number": "0123456789",
  "deduction_amount": "0.00",
  "deduction_reason": ""
}
```

---

### GET /api/v1/clients/export/

Downloads client list as CSV. Excludes `id_number` for privacy. Requires `md` or `admin_full`.

```http
GET /api/v1/clients/export/ HTTP/1.1
Authorization: Bearer <access_token>
```

**Expected response (200):** `Content-Type: text/csv`

---

## Phase 6 — Maintenance & Issue Escalation

> **Status: Pending** — endpoints available after Phase 6 implementation.

### POST /api/v1/maintenance/

Creates a maintenance request. `sla_deadline` is auto-calculated from priority.

```http
POST /api/v1/maintenance/ HTTP/1.1
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "issue_type": "electrical",
  "location_type": "property",
  "property": "ee0e8400-e29b-41d4-a716-446655440000",
  "location_details": "Master bedroom — ceiling fan sparking",
  "priority": "high",
  "description": "Ceiling fan in master bedroom emitting sparks when switched on. Potential fire hazard."
}
```

**Expected response (201):**
```json
{
  "id": "dd1e8400-e29b-41d4-a716-446655440000",
  "request_code": "MNT-2026-0001",
  "status": "open",
  "sla_deadline": "2026-03-06T14:30:00Z",
  "is_overdue": false
}
```

**SLA deadlines:** `critical` = +4h · `high` = +24h · `medium` = +72h · `low` = +7 days

---

### POST /api/v1/maintenance/{id}/assign/

```http
POST /api/v1/maintenance/dd1e8400-e29b-41d4-a716-446655440000/assign/ HTTP/1.1
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "assigned_to": "ee1e8400-e29b-41d4-a716-446655440000",
  "notes": "Please attend before 6pm today.",
  "expected_resolution_at": "2026-03-06T18:00:00Z"
}
```

**Expected response (200):**
```json
{
  "status": "assigned",
  "assigned_to": "ee1e8400-e29b-41d4-a716-446655440000"
}
```

---

### POST /api/v1/maintenance/{id}/accept/

Assignee accepts or declines.

**Accept:**
```http
POST /api/v1/maintenance/dd1e8400-e29b-41d4-a716-446655440000/accept/ HTTP/1.1
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "accepted": true
}
```

**Decline:**
```json
{
  "accepted": false,
  "decline_reason": "Specialist equipment required — not qualified for this issue type."
}
```

---

### POST /api/v1/maintenance/{id}/update-status/

Creates an append-only `MaintenanceStatusUpdate` record.

```http
POST /api/v1/maintenance/dd1e8400-e29b-41d4-a716-446655440000/update-status/ HTTP/1.1
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "to_status": "in_progress",
  "notes": "Work has started. Replaced faulty capacitor."
}
```

**Pending parts:**
```json
{
  "to_status": "pending_parts",
  "notes": "Need replacement fan motor.",
  "parts_needed": [{"item": "Ceiling Fan Motor 60W", "qty": 1}],
  "parts_vendor": "ElectroSupply Ltd",
  "parts_estimated_cost": "8500.00",
  "parts_expected_delivery": "2026-03-07"
}
```

**`to_status` values:** `in_progress` | `pending_parts` | `resolved`

---

### POST /api/v1/maintenance/{id}/close/

```http
POST /api/v1/maintenance/dd1e8400-e29b-41d4-a716-446655440000/close/ HTTP/1.1
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "verification_notes": "Issue resolved and verified. Fan operating normally."
}
```

**Expected response (200):**
```json
{
  "status": "closed",
  "resolved_at": "2026-03-06T16:45:00Z",
  "labor_hours": 2.5
}
```

---

### GET /api/v1/maintenance/metrics/

Returns aggregated maintenance KPIs. Requires `admin` or `md`.

```http
GET /api/v1/maintenance/metrics/ HTTP/1.1
Authorization: Bearer <access_token>
```

**Expected response (200):**
```json
{
  "avg_resolution_hours_by_priority": {
    "critical": 3.2,
    "high": 18.5,
    "medium": 60.0,
    "low": 120.0
  },
  "sla_breach_rate_pct": 12.5,
  "open_count": 4,
  "overdue_count": 1
}
```

---

## Phase 7 — Notification API

> **Status: Pending** — endpoints available after Phase 7 implementation.

### GET /api/v1/notifications/

Lists the current user's own notifications only. Filterable by `is_read`, `notification_type`.

```http
GET /api/v1/notifications/?is_read=false HTTP/1.1
Authorization: Bearer <access_token>
```

**Expected response (200):**
```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "ff1e8400-e29b-41d4-a716-446655440000",
      "notification_type": "approval_pending",
      "title": "New approval request",
      "body": "A project proposal requires your approval.",
      "resource_type": "approvalworkflow",
      "resource_id": "770e8400-e29b-41d4-a716-446655440000",
      "channel": "in_app",
      "is_read": false,
      "read_at": null,
      "created_at": "2026-03-05T14:30:00Z"
    }
  ]
}
```

**`notification_type` values:** `approval_pending` | `approval_decided` | `assignment` | `sla_warning` | `budget_alert` | `booking_reminder` | `system`

---

### GET /api/v1/notifications/unread-count/

```http
GET /api/v1/notifications/unread-count/ HTTP/1.1
Authorization: Bearer <access_token>
```

**Expected response (200):**
```json
{
  "count": 2
}
```

---

### POST /api/v1/notifications/{id}/read/

```http
POST /api/v1/notifications/ff1e8400-e29b-41d4-a716-446655440000/read/ HTTP/1.1
Authorization: Bearer <access_token>
```

**Expected response (200):**
```json
{
  "is_read": true,
  "read_at": "2026-03-05T15:00:00Z"
}
```

---

### POST /api/v1/notifications/read-all/

Marks all of the current user's unread notifications as read.

```http
POST /api/v1/notifications/read-all/ HTTP/1.1
Authorization: Bearer <access_token>
```

**Expected response (200):**
```json
{
  "updated": 2
}
```

---

## Common Error Responses

| Status | When |
|---|---|
| 400 | Invalid or missing payload fields |
| 401 | Missing or expired JWT |
| 403 | Valid JWT but insufficient role/permission |
| 404 | Resource does not exist |
| 409 | Duplicate resource or booking overlap |
| 423 | Account locked (too many failed login attempts) |
| 429 | Rate limit exceeded |

**Standard error envelope:**
```json
{
  "error": "error_code",
  "message": "Human-readable description.",
  "details": {}
}
```

**Standard paginated list envelope:**
```json
{
  "count": 100,
  "next": "http://localhost:8000/api/v1/users/?page=2",
  "previous": null,
  "results": []
}
```

---

## Role Quick Reference

| Role key | Typical access |
|---|---|
| `md` | Full system access |
| `hr_full` | Users, audit logs, approval decisions |
| `hr_limited` | View-only users (own dept) |
| `finance_full` | Payments, requisition approvals |
| `finance_limited` | View payments and requisitions |
| `admin_full` | Properties, clients, bookings, maintenance |
| `admin_limited` | View-only shortlets |
| `pm_full` | Full project management |
| `pm_limited` | View projects, add site reports |
| `front_desk` | Clients, bookings, check-in/check-out |

---

*Last updated: All phases complete — Swagger UI & ReDoc available at `/api/schema/`*
