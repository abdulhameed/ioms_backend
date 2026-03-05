
# IOMS Backend

Dockerised Django REST API for the Integrated Organisational Management System.

## Stack
- **Django 4.2 LTS** + Django REST Framework
- **PostgreSQL 15** (primary database)
- **Redis 7** (cache + Celery broker)
- **Celery 5** (async tasks + beat scheduler)

---

## Quick Start

### 1. Copy and configure environment
```bash
cp .env.example .env
# Edit .env — set DJANGO_SECRET_KEY, DB_PASSWORD, FERNET_KEY
```

### 2. Start services
```bash
make up       # starts db, redis, backend, celery_worker, celery_beat
make migrate  # run all DB migrations
make seed     # create the 13 permission groups
```

### 3. Create a superuser
```bash
make createsuperuser
```

### 4. Access the API
- API root: http://localhost:8000/api/v1/
- Health check: http://localhost:8000/api/v1/health/
- Django admin: http://localhost:8000/admin/

---

## Make Commands

| Command | Description |
|---|---|
| `make up` | Start all dev services |
| `make down` | Stop all services |
| `make build` | Rebuild Docker images |
| `make migrate` | Run DB migrations |
| `make makemigrations` | Generate new migration files |
| `make seed` | Create all 13 permission groups (idempotent) |
| `make test` | Run full test suite with coverage |
| `make test-phase N=2` | Run tests for a specific phase |
| `make shell` | Open Django shell_plus |
| `make logs` | Stream backend logs |
| `make lint` | Run flake8 + black check |
| `make createsuperuser` | Create Django admin superuser |
| `make collectstatic` | Collect static files |
| `make backup` | Dump PostgreSQL to timestamped SQL file |

---

## Environment Variables

See `.env.example` for the full list with descriptions.

| Variable | Required | Description |
|---|---|---|
| `DJANGO_SECRET_KEY` | Yes | 50+ char random string |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` | Yes | PostgreSQL credentials |
| `REDIS_URL` | Yes | Redis connection string |
| `FERNET_KEY` | Yes | 32-byte base64 key for field encryption |
| `DJANGO_SETTINGS_MODULE` | Yes | `config.settings.development` or `production` |

---

## Testing

```bash
make test                  # full suite with coverage
make test-phase N=2        # Phase 2 tests only (AUTH-01 to AUTH-15)
make test-phase N=3        # Phase 3 tests only (APR-01 to APR-10)
```

Tests require a running database. Use `make up` first.

---

## Project Structure

```
ioms_backend/
├── docker-compose.yml         # Dev: db, redis, backend, celery_worker, celery_beat
├── docker-compose.prod.yml    # Prod: adds nginx, uses gunicorn
├── .env.example               # Copy to .env and fill in values
├── Makefile                   # Dev shortcuts
├── docs/
│   └── milestone_1_PRD_v2.md  # Implementation PRD with phase-by-phase plan
├── nginx/
│   └── nginx.conf             # Production reverse proxy config
└── backend/
    ├── Dockerfile             # Multi-stage: development + production targets
    ├── requirements.txt       # Pinned production dependencies
    ├── requirements.dev.txt   # Dev dependencies (includes requirements.txt)
    ├── manage.py
    ├── config/                # Django project package
    │   ├── settings/
    │   │   ├── base.py        # Shared settings
    │   │   ├── development.py # DEBUG=True, dev tools
    │   │   └── production.py  # DEBUG=False, HTTPS, S3, Sentry
    │   ├── urls.py
    │   ├── celery.py
    │   ├── wsgi.py
    │   └── asgi.py
    ├── apps/
    │   ├── core/              # Health check, API root, shared utilities
    │   ├── users/             # Auth, RBAC, AuditLog, Notification model
    │   ├── approvals/         # Approval workflow engine
    │   ├── projects/          # Projects, milestones, site reports, requisitions
    │   ├── shortlets/         # Properties, clients, bookings, caution deposits
    │   ├── maintenance/       # Maintenance requests + SLA tracking
    │   └── notifications/     # Notification API endpoints + Celery tasks
    └── tests/
        ├── conftest.py
        ├── test_auth.py
        ├── test_projects.py
        ├── test_shortlets.py
        └── test_maintenance.py
```