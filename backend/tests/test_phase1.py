"""
Phase 1 — Infrastructure smoke tests.
These run against the live Docker stack (db + redis + backend).
"""

import pytest


@pytest.mark.phase1
@pytest.mark.django_db
def test_api_root_returns_200(client):
    response = client.get('/api/v1/')
    assert response.status_code == 200


@pytest.mark.phase1
@pytest.mark.django_db
def test_api_root_json_structure(client):
    response = client.get('/api/v1/')
    data = response.json()
    assert data['status'] == 'operational'
    assert data['version'] == 'v1'
    assert 'api' in data


@pytest.mark.phase1
@pytest.mark.django_db
def test_health_check_returns_200(client):
    response = client.get('/api/v1/health/')
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'ok'
    assert data['db'] == 'ok'
    assert data['redis'] == 'ok'


@pytest.mark.phase1
@pytest.mark.django_db
def test_seed_groups_creates_13_groups(db):
    from django.contrib.auth.models import Group
    from apps.users.management.commands.seed_groups import GROUPS, Command

    Command().handle()
    assert Group.objects.filter(name__in=GROUPS).count() == 13


@pytest.mark.phase1
@pytest.mark.django_db
def test_seed_groups_is_idempotent(db):
    from django.contrib.auth.models import Group
    from apps.users.management.commands.seed_groups import GROUPS, Command

    Command().handle()
    Command().handle()  # second run
    assert Group.objects.filter(name__in=GROUPS).count() == 13
