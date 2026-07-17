"""Tests der Anmeldung: Erfolg, Fehlschlag, gesperrter Mandant, Rate-Limit."""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.audit.models import AuditAction, AuditLog
from apps.core.models import Tenant

pytestmark = pytest.mark.django_db

LOGIN_URL = reverse("accounts:login")


def test_erfolgreiche_anmeldung_leitet_zum_dashboard(admin_a: User) -> None:
    client = Client()
    response = client.post(
        LOGIN_URL, {"email": "admin-a@example.com", "password": "pw-admin-a-123"}
    )
    assert response.status_code == 302
    assert response.url == reverse("core:dashboard")
    assert AuditLog.objects.filter(action=AuditAction.LOGIN, actor=admin_a).exists()


def test_falsches_passwort_wird_protokolliert(admin_a: User) -> None:
    client = Client()
    response = client.post(LOGIN_URL, {"email": "admin-a@example.com", "password": "falsch"})
    assert response.status_code == 200
    assert b"falsch" in response.content.lower()
    failed = AuditLog.objects.filter(action=AuditAction.LOGIN_FAILED)
    assert failed.count() == 1
    assert failed.first().changes.get("email") == "admin-a@example.com"


def test_gesperrter_mandant_verhindert_anmeldung(admin_a: User, tenant_a: Tenant) -> None:
    tenant_a.is_active = False
    tenant_a.save(update_fields=["is_active"])

    client = Client()
    response = client.post(
        LOGIN_URL, {"email": "admin-a@example.com", "password": "pw-admin-a-123"}
    )
    assert response.status_code == 200  # bleibt auf der Anmeldeseite
    assert "_auth_user_id" not in client.session


def test_rate_limit_greift_nach_zu_vielen_versuchen(admin_a: User) -> None:
    client = Client()
    # E-Mail-Rate ist 5/min; der sechste Versuch wird begrenzt.
    for _ in range(5):
        client.post(LOGIN_URL, {"email": "admin-a@example.com", "password": "falsch"})
    response = client.post(LOGIN_URL, {"email": "admin-a@example.com", "password": "falsch"})
    assert response.status_code == 200
    assert "zu viele" in response.content.decode().lower()


def test_bereits_angemeldet_wird_umgeleitet(admin_a_client: Client) -> None:
    response = admin_a_client.get(LOGIN_URL)
    assert response.status_code == 302
    assert response.url == reverse("core:dashboard")


def test_abmeldung_nur_per_post(admin_a_client: Client) -> None:
    # GET meldet nicht ab ...
    admin_a_client.get(reverse("accounts:logout"))
    assert "_auth_user_id" in admin_a_client.session
    # ... POST schon.
    response = admin_a_client.post(reverse("accounts:logout"))
    assert response.status_code == 302
    assert "_auth_user_id" not in admin_a_client.session
    assert AuditLog.objects.filter(action=AuditAction.LOGOUT).exists()
