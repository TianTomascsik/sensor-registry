"""Tests der Mandantenverwaltung und des Mandanten-Umschalters (Superadmin)."""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

from apps.audit.models import AuditAction, AuditLog
from apps.core.middleware import ACTIVE_TENANT_SESSION_KEY
from apps.core.models import Tenant

pytestmark = pytest.mark.django_db


def test_superadmin_legt_mandanten_an(superadmin_client: Client) -> None:
    response = superadmin_client.post(
        reverse("core:tenant_create"),
        {"name": "Neue Firma", "slug": "neue-firma", "gps_accuracy_threshold_m": 7},
    )
    assert response.status_code == 302
    tenant = Tenant.objects.get(slug="neue-firma")
    assert tenant.gps_accuracy_threshold_m == 7
    assert AuditLog.objects.filter(
        action=AuditAction.TENANT_CREATED, object_id=str(tenant.pk)
    ).exists()


def test_doppeltes_kuerzel_wird_abgelehnt(superadmin_client: Client, tenant_a: Tenant) -> None:
    response = superadmin_client.post(
        reverse("core:tenant_create"),
        {"name": "Andere", "slug": "firma-a", "gps_accuracy_threshold_m": 5},
    )
    assert response.status_code == 200
    assert Tenant.objects.filter(name="Andere").count() == 0


def test_superadmin_aktualisiert_mandanten(superadmin_client: Client, tenant_a: Tenant) -> None:
    response = superadmin_client.post(
        reverse("core:tenant_update", args=[tenant_a.pk]),
        {"name": "Firma A neu", "gps_accuracy_threshold_m": 3},
    )
    assert response.status_code == 302
    tenant_a.refresh_from_db()
    assert tenant_a.name == "Firma A neu"
    assert tenant_a.gps_accuracy_threshold_m == 3
    log = AuditLog.objects.filter(action=AuditAction.TENANT_UPDATED).first()
    assert log is not None
    assert log.changes["name"]["zu"] == "Firma A neu"


def test_deaktivierter_mandant_wird_aus_auswahl_entfernt(
    superadmin_client: Client, tenant_a: Tenant
) -> None:
    session = superadmin_client.session
    session[ACTIVE_TENANT_SESSION_KEY] = tenant_a.pk
    session.save()

    superadmin_client.post(reverse("core:tenant_toggle_active", args=[tenant_a.pk]))
    tenant_a.refresh_from_db()
    assert tenant_a.is_active is False
    assert ACTIVE_TENANT_SESSION_KEY not in superadmin_client.session


def test_mandant_umschalten_setzt_und_loescht_auswahl(
    superadmin_client: Client, tenant_a: Tenant
) -> None:
    superadmin_client.post(reverse("core:tenant_switch"), {"tenant": str(tenant_a.pk)})
    assert superadmin_client.session[ACTIVE_TENANT_SESSION_KEY] == tenant_a.pk

    superadmin_client.post(reverse("core:tenant_switch"), {"tenant": ""})
    assert ACTIVE_TENANT_SESSION_KEY not in superadmin_client.session


def test_mandantenadmin_hat_keinen_zugriff_auf_mandantenverwaltung(
    admin_a_client: Client,
) -> None:
    assert admin_a_client.get(reverse("core:tenant_list")).status_code == 403
    assert admin_a_client.post(reverse("core:tenant_switch")).status_code == 403


def test_anonymer_zugriff_wird_zur_anmeldung_geleitet() -> None:
    client = Client()
    response = client.get(reverse("core:tenant_list"))
    assert response.status_code == 302
    assert reverse("accounts:login") in response.url
