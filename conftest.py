"""Projektweite Test-Fixtures.

Stellt Mandanten und Benutzer der drei Rollen bereit sowie angemeldete Test-Clients.
Die Fixtures dienen als Grundlage für die Mandanten-Isolationstests und die
Funktionstests der Verwaltung.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from django.core.cache import cache
from django.test import Client

from apps.accounts.models import Role, User
from apps.core.models import Tenant


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    """Setzt den Cache vor jedem Test zurück (isoliert den Rate-Limit-Zustand)."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def superadmin(db) -> User:
    return User.objects.create_superuser(
        email="root@example.com", password="pw-root-123", full_name="Super Admin"
    )


@pytest.fixture
def tenant_a(db) -> Tenant:
    return Tenant.objects.create(name="Firma A", slug="firma-a", gps_accuracy_threshold_m=5)


@pytest.fixture
def tenant_b(db) -> Tenant:
    return Tenant.objects.create(name="Firma B", slug="firma-b", gps_accuracy_threshold_m=8)


@pytest.fixture
def admin_a(tenant_a: Tenant) -> User:
    return User.objects.create_user(
        email="admin-a@example.com",
        password="pw-admin-a-123",
        full_name="Admin A",
        role=Role.TENANT_ADMIN,
        tenant=tenant_a,
    )


@pytest.fixture
def admin_b(tenant_b: Tenant) -> User:
    return User.objects.create_user(
        email="admin-b@example.com",
        password="pw-admin-b-123",
        full_name="Admin B",
        role=Role.TENANT_ADMIN,
        tenant=tenant_b,
    )


@pytest.fixture
def installer_a(tenant_a: Tenant) -> User:
    return User.objects.create_user(
        email="monteur-a@example.com",
        password=None,
        full_name="Monteur A",
        role=Role.INSTALLER,
        tenant=tenant_a,
    )


def _login(client: Client, email: str, password: str) -> Client:
    assert client.login(username=email, password=password)
    return client


@pytest.fixture
def superadmin_client(superadmin: User) -> Client:
    return _login(Client(), "root@example.com", "pw-root-123")


@pytest.fixture
def admin_a_client(admin_a: User) -> Client:
    return _login(Client(), "admin-a@example.com", "pw-admin-a-123")


@pytest.fixture
def admin_b_client(admin_b: User) -> Client:
    return _login(Client(), "admin-b@example.com", "pw-admin-b-123")
