"""Tests der Benutzerverwaltung inkl. Mandanten-Isolation."""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.audit.models import AuditAction, AuditLog
from apps.core.middleware import ACTIVE_TENANT_SESSION_KEY
from apps.core.models import Tenant

pytestmark = pytest.mark.django_db


def test_mandantenadmin_sieht_nur_eigene_benutzer(
    admin_a_client: Client, admin_a: User, admin_b: User
) -> None:
    response = admin_a_client.get(reverse("accounts:user_list"))
    assert response.status_code == 200
    names = {u.pk for u in response.context["users"]}
    assert admin_a.pk in names
    assert admin_b.pk not in names


def test_mandantenadmin_kann_fremden_benutzer_nicht_bearbeiten(
    admin_a_client: Client, admin_b: User
) -> None:
    response = admin_a_client.get(reverse("accounts:user_update", args=[admin_b.pk]))
    assert response.status_code == 404


def test_mandantenadmin_kann_fremden_benutzer_nicht_deaktivieren(
    admin_a_client: Client, admin_b: User
) -> None:
    response = admin_a_client.post(reverse("accounts:user_toggle_active", args=[admin_b.pk]))
    assert response.status_code == 404
    admin_b.refresh_from_db()
    assert admin_b.is_active is True


def test_benutzer_anlegen_erzeugt_benutzer_im_eigenen_mandanten(
    admin_a_client: Client, tenant_a: Tenant
) -> None:
    response = admin_a_client.post(
        reverse("accounts:user_create"),
        {
            "full_name": "Neuer Monteur",
            "email": "neu@example.com",
            "role": Role.INSTALLER.value,
            "password": "",
        },
    )
    assert response.status_code == 302
    created = User.objects.get(email="neu@example.com")
    assert created.tenant_id == tenant_a.pk
    assert created.role == Role.INSTALLER
    # Monteur ohne Passwort: unbenutzbar, Zugang später per Geräteanmeldung.
    assert created.has_usable_password() is False
    assert AuditLog.objects.filter(
        action=AuditAction.USER_CREATED, object_id=str(created.pk)
    ).exists()


def test_mandantenadmin_ohne_passwort_fuer_admin_rolle_wird_abgelehnt(
    admin_a_client: Client,
) -> None:
    response = admin_a_client.post(
        reverse("accounts:user_create"),
        {
            "full_name": "Admin ohne PW",
            "email": "adminohnepw@example.com",
            "role": Role.TENANT_ADMIN.value,
            "password": "",
        },
    )
    assert response.status_code == 200  # Formular mit Fehler
    assert not User.objects.filter(email="adminohnepw@example.com").exists()


def test_benutzer_deaktivieren_und_reaktivieren(admin_a_client: Client, tenant_a: Tenant) -> None:
    target = User.objects.create_user(
        email="ziel@example.com",
        password="pw-ziel-123",
        full_name="Ziel",
        role=Role.INSTALLER,
        tenant=tenant_a,
    )
    url = reverse("accounts:user_toggle_active", args=[target.pk])

    admin_a_client.post(url)
    target.refresh_from_db()
    assert target.is_active is False
    assert AuditLog.objects.filter(action=AuditAction.USER_DEACTIVATED).exists()

    admin_a_client.post(url)
    target.refresh_from_db()
    assert target.is_active is True
    assert AuditLog.objects.filter(action=AuditAction.USER_ACTIVATED).exists()


def test_superadmin_muss_mandanten_waehlen_bevor_er_benutzer_anlegt(
    superadmin_client: Client,
) -> None:
    # Ohne gewählten Mandanten (Gesamtsicht) ist kein Anlegen möglich.
    response = superadmin_client.get(reverse("accounts:user_create"))
    assert response.status_code == 302
    assert response.url == reverse("accounts:user_list")


def test_superadmin_legt_benutzer_im_gewaehlten_mandanten_an(
    superadmin_client: Client, tenant_a: Tenant
) -> None:
    session = superadmin_client.session
    session[ACTIVE_TENANT_SESSION_KEY] = tenant_a.pk
    session.save()

    response = superadmin_client.post(
        reverse("accounts:user_create"),
        {
            "full_name": "Von Superadmin",
            "email": "vonsuper@example.com",
            "role": Role.TENANT_ADMIN.value,
            "password": "pw-super-neu-123",
        },
    )
    assert response.status_code == 302
    created = User.objects.get(email="vonsuper@example.com")
    assert created.tenant_id == tenant_a.pk


def test_installer_hat_keinen_zugriff_auf_benutzerverwaltung(installer_a: User) -> None:
    client = Client()
    client.force_login(installer_a)
    response = client.get(reverse("accounts:user_list"))
    assert response.status_code == 403
