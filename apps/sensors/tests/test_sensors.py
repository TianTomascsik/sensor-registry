"""Tests der Sensorverwaltung: Isolation, Normalisierung, CRUD, Berechtigungen."""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

from apps.audit.models import AuditAction, AuditLog
from apps.core.models import Tenant
from apps.core.tenancy import tenant_context
from apps.sensors.models import Sensor, normalize_deveui

pytestmark = pytest.mark.django_db


def _make_sensor(tenant: Tenant, dev_eui: str) -> Sensor:
    with tenant_context(tenant):
        return Sensor.objects.create(dev_eui=dev_eui)


def test_normalize_deveui_entfernt_trennzeichen_und_grossschreibung() -> None:
    assert normalize_deveui("70:b3:d5:7e:d0:01:23:45") == "70B3D57ED0012345"
    assert normalize_deveui(" 70b3d5-7ed0012345 ") == "70B3D57ED0012345"


def test_deveui_wird_beim_speichern_normalisiert(tenant_a: Tenant) -> None:
    sensor = _make_sensor(tenant_a, "70:b3:d5:7e:d0:01:23:45")
    assert sensor.dev_eui == "70B3D57ED0012345"


def test_deveui_pro_mandant_eindeutig_aber_mandantenuebergreifend_erlaubt(
    tenant_a: Tenant, tenant_b: Tenant
) -> None:
    _make_sensor(tenant_a, "AAAAAAAAAAAAAAAA")
    # Gleicher DevEUI in anderem Mandanten ist erlaubt.
    _make_sensor(tenant_b, "AAAAAAAAAAAAAAAA")
    with tenant_context(tenant_a):
        assert Sensor.objects.count() == 1
    with tenant_context(tenant_b):
        assert Sensor.objects.count() == 1


def test_doppelter_deveui_im_mandanten_scheitert(tenant_a: Tenant) -> None:
    from django.db import IntegrityError

    _make_sensor(tenant_a, "BBBBBBBBBBBBBBBB")
    with tenant_context(tenant_a):
        with pytest.raises(IntegrityError):
            Sensor.objects.create(dev_eui="BBBBBBBBBBBBBBBB")


def test_admin_legt_sensor_an(admin_a_client: Client, tenant_a: Tenant) -> None:
    response = admin_a_client.post(
        reverse("sensors:create"),
        {
            "dev_eui": "70:B3:D5:7E:D0:01:23:45",
            "manufacturer": "Dragino",
            "sensor_type": "LSE01",
            "serial_number": "SN-1",
            "note": "",
        },
    )
    assert response.status_code == 302
    with tenant_context(tenant_a):
        sensor = Sensor.objects.get(dev_eui="70B3D57ED0012345")
        assert sensor.manufacturer == "Dragino"
        assert sensor.tenant_id == tenant_a.pk
    assert AuditLog.objects.filter(action=AuditAction.SENSOR_CREATED).exists()


def test_doppelter_deveui_wird_im_formular_abgelehnt(
    admin_a_client: Client, tenant_a: Tenant
) -> None:
    _make_sensor(tenant_a, "CCCCCCCCCCCCCCCC")
    response = admin_a_client.post(
        reverse("sensors:create"),
        {
            "dev_eui": "cccccccccccccccc",
            "manufacturer": "",
            "sensor_type": "",
            "serial_number": "",
            "note": "",
        },
    )
    assert response.status_code == 200
    with tenant_context(tenant_a):
        assert Sensor.objects.count() == 1


def test_ungueltiger_deveui_wird_abgelehnt(admin_a_client: Client, tenant_a: Tenant) -> None:
    response = admin_a_client.post(
        reverse("sensors:create"),
        {
            "dev_eui": "XYZ123",
            "manufacturer": "",
            "sensor_type": "",
            "serial_number": "",
            "note": "",
        },
    )
    assert response.status_code == 200
    with tenant_context(tenant_a):
        assert Sensor.objects.count() == 0


def test_admin_bearbeitet_und_loescht_sensor(admin_a_client: Client, tenant_a: Tenant) -> None:
    sensor = _make_sensor(tenant_a, "DDDDDDDDDDDDDDDD")

    admin_a_client.post(
        reverse("sensors:update", args=[sensor.pk]),
        {"manufacturer": "Neu", "sensor_type": "T1", "serial_number": "", "note": ""},
    )
    sensor.refresh_from_db()
    assert sensor.manufacturer == "Neu"

    admin_a_client.post(reverse("sensors:delete", args=[sensor.pk]))
    with tenant_context(tenant_a):
        assert not Sensor.objects.filter(pk=sensor.pk).exists()
    assert AuditLog.objects.filter(action=AuditAction.SENSOR_DELETED).exists()


def test_admin_kann_fremden_sensor_nicht_bearbeiten(
    admin_a_client: Client, tenant_b: Tenant
) -> None:
    foreign = _make_sensor(tenant_b, "EEEEEEEEEEEEEEEE")
    assert admin_a_client.get(reverse("sensors:update", args=[foreign.pk])).status_code == 404


def test_monteur_hat_keinen_zugriff_auf_sensoren(installer_a_client: Client) -> None:
    assert installer_a_client.get(reverse("sensors:list")).status_code == 403
    assert installer_a_client.get(reverse("sensors:create")).status_code == 403


def test_suche_filtert_sensoren(admin_a_client: Client, tenant_a: Tenant) -> None:
    with tenant_context(tenant_a):
        Sensor.objects.create(dev_eui="1111111111111111", manufacturer="Dragino")
        Sensor.objects.create(dev_eui="2222222222222222", manufacturer="Milesight")
    response = admin_a_client.get(reverse("sensors:list"), {"q": "Milesight"})
    euis = {s.dev_eui for s in response.context["sensors"]}
    assert euis == {"2222222222222222"}
