.PHONY: up down build migrate makemigrations seed test test-phase shell logs lint createsuperuser collectstatic backup

# ── Services ──────────────────────────────────────────────────────────────────

up:
	docker-compose up -d

down:
	docker-compose down

build:
	docker-compose build

# ── Database ───────────────────────────────────────────────────────────────────

migrate:
	docker-compose exec backend python manage.py migrate

makemigrations:
	docker-compose exec backend python manage.py makemigrations

seed:
	docker-compose exec backend python manage.py seed_groups

# ── Tests ──────────────────────────────────────────────────────────────────────

test:
	docker-compose exec backend pytest --cov=apps --cov-report=term-missing

# Usage: make test-phase N=2
test-phase:
	docker-compose exec backend pytest -m phase$(N) -v

# ── Dev tools ─────────────────────────────────────────────────────────────────

shell:
	docker-compose exec backend python manage.py shell_plus

logs:
	docker-compose logs -f backend

lint:
	docker-compose exec backend flake8 apps/ && docker-compose exec backend black apps/ --check

createsuperuser:
	docker-compose exec backend python manage.py createsuperuser

collectstatic:
	docker-compose exec backend python manage.py collectstatic --noinput

# ── Backup ────────────────────────────────────────────────────────────────────

backup:
	docker-compose exec db pg_dump -U $${DB_USER} $${DB_NAME} > backup_$$(date +%Y%m%d_%H%M%S).sql
