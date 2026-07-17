"""Tests der Referenzdaten-API (Offline-Replikat) inkl. Mandanten-/Rollen-Isolation."""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.devices import generate_token, hash_token
from apps.accounts.models import Device, User
from apps.core.models import Tenant
from apps.core.tenancy import tenant_context
from apps.projects.models import Project, ProjectAssignment
from apps.sensors.models import Sensor

pytestmark = pytest.mark.django_db

COOKIE = "device_token"


@pytest.fixture
def scenario(tenant_a: Tenant, tenant_b: Tenant, installer_a: User):
    with tenant_context(tenant_a):
        assigned = Project.objects.create(number="A-1", name="Zugewiesen", status="active")
        Project.objects.create(number="A-2", name="Nicht zugewiesen", status="active")
        Sensor.objects.create(dev_eui="AAAAAAAAAAAAAAAA")
        ProjectAssignment.objects.create(project=assigned, user=installer_a)
    with tenant_context(tenant_b):
        Project.objects.create(number="B-1", name="Fremd", status="active")
        Sensor.objects.create(dev_eui="BBBBBBBBBBBBBBBB")
    return {"assigned": assigned}


def _device_client(installer: User) -> Client:
    raw = generate_token()
    Device.objects.create(
        tenant=installer.tenant, user=installer, token_hash=hash_token(raw), label="G"
    )
    client = Client()
    client.cookies[COOKIE] = raw
    return client


def test_refdata_monteur_sieht_nur_zugewiesene_projekte(scenario: dict, installer_a: User) -> None:
    client = _device_client(installer_a)
    response = client.get(reverse("api:refdata"))
    assert response.status_code == 200
    data = response.json()
    numbers = {p["number"] for p in data["projects"]}
    assert numbers == {"A-1"}  # nur das zugewiesene Projekt des eigenen Mandanten
    euis = {s["dev_eui"] for s in data["sensors"]}
    assert euis == {"AAAAAAAAAAAAAAAA"}  # nur Sensoren des eigenen Mandanten


def test_refdata_admin_sieht_alle_projekte_des_mandanten(
    scenario: dict, admin_a_client: Client
) -> None:
    response = admin_a_client.get(reverse("api:refdata"))
    data = response.json()
    numbers = {p["number"] for p in data["projects"]}
    assert numbers == {"A-1", "A-2"}


def test_refdata_ist_mandantengetrennt(scenario: dict, admin_b_client: Client) -> None:
    data = admin_b_client.get(reverse("api:refdata")).json()
    assert {p["number"] for p in data["projects"]} == {"B-1"}
    assert {s["dev_eui"] for s in data["sensors"]} == {"BBBBBBBBBBBBBBBB"}


def test_refdata_erfordert_authentifizierung() -> None:
    response = Client().get(reverse("api:refdata"))
    assert response.status_code in (401, 403)
