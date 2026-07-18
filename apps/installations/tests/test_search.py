"""Tests der globalen Suche und der Kartenansicht (Phase 5)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import Tenant
from apps.core.tenancy import tenant_context
from apps.installations.services import create_installation
from apps.projects.models import Project
from apps.sensors.models import Sensor

pytestmark = pytest.mark.django_db


@pytest.fixture
def data(tenant_a: Tenant, installer_a: User):
    """Zwei Installationen mit unterschiedlichen Merkmalen im Mandanten A."""
    with tenant_context(tenant_a):
        project1 = Project.objects.create(number="P-1", name="Nordfeld", status="active")
        project2 = Project.objects.create(number="P-2", name="Südfeld", status="active")
        sensor1 = Sensor.objects.create(dev_eui="AAAAAAAAAAAAAAAA")
        sensor2 = Sensor.objects.create(dev_eui="BBBBBBBBBBBBBBBB")

    def _make(sensor, project, description):
        with tenant_context(tenant_a):
            inst, _ = create_installation(
                client_uuid=uuid.uuid4(),
                sensor=sensor,
                project=project,
                installer=installer_a,
                latitude=Decimal("47.1"),
                longitude=Decimal("8.2"),
                accuracy_m=3.0,
                captured_at=timezone.now(),
                description=description,
                actor=installer_a,
            )
        return inst

    return {
        "project1": project1,
        "project2": project2,
        "a": _make(sensor1, project1, "Bodenfeuchte am Waldrand"),
        "b": _make(sensor2, project2, "Temperatur im Gewächshaus"),
    }


def _pks(response) -> set[int]:
    return {i.pk for i in response.context["installations"]}


def test_suche_nach_beschreibung(admin_a_client: Client, data: dict) -> None:
    response = admin_a_client.get(reverse("installations:search"), {"q": "Waldrand"})
    assert _pks(response) == {data["a"].pk}


def test_suche_nach_deveui(admin_a_client: Client, data: dict) -> None:
    response = admin_a_client.get(reverse("installations:search"), {"deveui": "BBBB"})
    assert _pks(response) == {data["b"].pk}


def test_filter_nach_projekt(admin_a_client: Client, data: dict) -> None:
    response = admin_a_client.get(reverse("installations:search"), {"project": data["project2"].pk})
    assert _pks(response) == {data["b"].pk}


def test_filter_nach_benutzer(admin_a_client: Client, data: dict, installer_a: User) -> None:
    response = admin_a_client.get(reverse("installations:search"), {"installer": installer_a.pk})
    assert _pks(response) == {data["a"].pk, data["b"].pk}


def test_zeitraum_filter_grenzt_ein(admin_a_client: Client, data: dict) -> None:
    # Zukünftiges Von-Datum → keine Ergebnisse.
    response = admin_a_client.get(reverse("installations:search"), {"date_from": "2099-01-01"})
    assert _pks(response) == set()


def test_suche_ist_mandantengetrennt(admin_b_client: Client, data: dict) -> None:
    # Admin eines anderen Mandanten sieht keine Installationen aus Mandant A.
    response = admin_b_client.get(reverse("installations:search"), {"q": "Waldrand"})
    assert _pks(response) == set()


def test_karten_und_suchseite_rendern(admin_a_client: Client, data: dict) -> None:
    assert admin_a_client.get(reverse("installations:map")).status_code == 200
    assert admin_a_client.get(reverse("installations:search")).status_code == 200


@override_settings(
    MAP_TILE_URL="https://tiles.example.com/{z}/{x}/{y}.png?key=abc",
    MAP_TILE_MAX_ZOOM=17,
)
def test_karte_nutzt_konfigurierte_tile_quelle(admin_a_client: Client, data: dict) -> None:
    """Die Tile-Quelle ist über Einstellungen konfigurierbar (Prod: eigener Provider)."""
    html = admin_a_client.get(reverse("installations:map")).content.decode()
    assert 'data-tile-url="https://tiles.example.com/{z}/{x}/{y}.png?key=abc"' in html
    assert 'data-tile-max-zoom="17"' in html
