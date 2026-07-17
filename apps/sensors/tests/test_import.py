"""Tests des CSV-Sensorimports (Validierung, Duplikate, Trennzeichen, Isolation)."""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.audit.models import AuditAction, AuditLog
from apps.core.models import Tenant
from apps.core.tenancy import tenant_context
from apps.sensors.models import Sensor
from apps.sensors.services import import_sensors_from_csv

pytestmark = pytest.mark.django_db


def _import(tenant: Tenant, actor: User, csv_text: str):
    with tenant_context(tenant):
        return import_sensors_from_csv(data=csv_text.encode("utf-8"), actor=actor)


def test_gueltiger_import_legt_sensoren_an(tenant_a: Tenant, admin_a: User) -> None:
    csv_text = (
        "DevEUI,Hersteller,Typ,Seriennummer,Bemerkung\n"
        "70B3D57ED0012345,Dragino,LSE01,SN-1,Feld A\n"
        "70:B3:D5:7E:D0:01:23:46,Milesight,EM500,SN-2,Feld B\n"
    )
    report = _import(tenant_a, admin_a, csv_text)
    assert report.created == 2
    assert report.error_count == 0
    with tenant_context(tenant_a):
        assert Sensor.objects.count() == 2
        sensor = Sensor.objects.get(dev_eui="70B3D57ED0012346")
        assert sensor.manufacturer == "Milesight"
    assert AuditLog.objects.filter(action=AuditAction.SENSOR_IMPORTED).exists()


def test_semikolon_trennzeichen_wird_erkannt(tenant_a: Tenant, admin_a: User) -> None:
    csv_text = "DevEUI;Hersteller\n1111111111111111;Dragino\n2222222222222222;Milesight\n"
    report = _import(tenant_a, admin_a, csv_text)
    assert report.created == 2


def test_duplikat_in_datei_wird_uebersprungen(tenant_a: Tenant, admin_a: User) -> None:
    csv_text = "DevEUI\nAAAAAAAAAAAAAAAA\naaaaaaaaaaaaaaaa\n"  # zweimal derselbe (normalisiert)
    report = _import(tenant_a, admin_a, csv_text)
    assert report.created == 1
    assert report.skipped_duplicate == 1


def test_bereits_vorhandener_sensor_wird_uebersprungen(tenant_a: Tenant, admin_a: User) -> None:
    with tenant_context(tenant_a):
        Sensor.objects.create(dev_eui="BBBBBBBBBBBBBBBB")
    report = _import(tenant_a, admin_a, "DevEUI\nBBBBBBBBBBBBBBBB\nCCCCCCCCCCCCCCCC\n")
    assert report.created == 1
    assert report.skipped_existing == 1


def test_ungueltige_zeile_erscheint_im_fehlerbericht(tenant_a: Tenant, admin_a: User) -> None:
    csv_text = "DevEUI\nGGGGGGGGGGGGGGGG\n1234567890ABCDEF\n"  # G ist kein Hex
    report = _import(tenant_a, admin_a, csv_text)
    assert report.created == 1
    assert report.error_count == 1
    assert report.errors[0].line == 2  # Zeile 1 = Kopfzeile


def test_fehlende_deveui_spalte_ist_fataler_fehler(tenant_a: Tenant, admin_a: User) -> None:
    report = _import(tenant_a, admin_a, "Hersteller,Typ\nDragino,LSE01\n")
    assert report.has_fatal_error
    assert report.created == 0


def test_import_ist_mandantengetrennt(
    tenant_a: Tenant, tenant_b: Tenant, admin_a: User, admin_b: User
) -> None:
    # Derselbe DevEUI existiert bereits in Mandant B ...
    with tenant_context(tenant_b):
        Sensor.objects.create(dev_eui="ABCDEF0123456789")
    # ... und lässt sich dennoch in Mandant A importieren (Eindeutigkeit ist pro Mandant).
    report = _import(tenant_a, admin_a, "DevEUI\nABCDEF0123456789\n")
    assert report.created == 1
    with tenant_context(tenant_a):
        assert Sensor.objects.filter(dev_eui="ABCDEF0123456789").count() == 1


def test_import_ueber_view(admin_a_client: Client, tenant_a: Tenant) -> None:
    upload = SimpleUploadedFile(
        "sensoren.csv",
        b"DevEUI,Hersteller\n1010101010101010,Dragino\n",
        content_type="text/csv",
    )
    response = admin_a_client.post(reverse("sensors:import"), {"file": upload})
    assert response.status_code == 200
    report = response.context["report"]
    assert report.created == 1
    with tenant_context(tenant_a):
        assert Sensor.objects.filter(dev_eui="1010101010101010").exists()
