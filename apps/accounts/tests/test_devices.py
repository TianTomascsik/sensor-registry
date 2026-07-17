"""Tests der passwortlosen Geräteanmeldung.

Deckt ab: Einladung erstellen/einlösen (atomar), Registrierungs-Flow, Geräte-
Authentifizierung per Cookie, sofort wirksames Sperren, Ablauf, last_seen-Drosselung,
Mandanten-Isolation und Berechtigungen.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.devices import (
    InviteRedemptionError,
    authenticate_device,
    create_invite,
    generate_token,
    hash_token,
    redeem_invite,
    touch_last_seen,
)
from apps.accounts.models import Device, DeviceInvite, User
from apps.audit.models import AuditAction, AuditLog
from apps.core.models import Tenant
from apps.core.tenancy import tenant_context
from apps.projects.models import Project, ProjectAssignment, ProjectStatus

pytestmark = pytest.mark.django_db

COOKIE = settings.DEVICE_TOKEN_COOKIE_NAME


def _register_device(installer: User, label: str = "Testgerät") -> tuple[Device, str]:
    """Registriert direkt ein Gerät (umgeht den View-Flow) und gibt (Gerät, Token) zurück."""
    raw = generate_token()
    device = Device.objects.create(
        tenant=installer.tenant, user=installer, token_hash=hash_token(raw), label=label
    )
    return device, raw


def _device_client(raw_token: str) -> Client:
    client = Client()
    client.cookies[COOKIE] = raw_token
    return client


# --- Service: Einladung & Authentifizierung ----------------------------------------


def test_hash_ist_deterministisch_und_token_einzigartig() -> None:
    token = generate_token()
    assert hash_token(token) == hash_token(token)
    assert generate_token() != generate_token()


def test_einladung_nur_fuer_monteure(admin_a: User, tenant_a: Tenant) -> None:
    with tenant_context(tenant_a):
        with pytest.raises(InviteRedemptionError):
            create_invite(user=admin_a, actor=admin_a)


def test_authenticate_device_gueltig_und_gesperrt(installer_a: User) -> None:
    device, raw = _register_device(installer_a)
    assert authenticate_device(raw) == device
    assert authenticate_device("falscher-token") is None

    device.revoked_at = timezone.now()
    device.save(update_fields=["revoked_at"])
    assert authenticate_device(raw) is None


def test_authenticate_device_bei_inaktivem_benutzer(installer_a: User) -> None:
    _device, raw = _register_device(installer_a)
    installer_a.is_active = False
    installer_a.save(update_fields=["is_active"])
    assert authenticate_device(raw) is None


def test_authenticate_device_bei_inaktivem_mandanten(installer_a: User, tenant_a: Tenant) -> None:
    _device, raw = _register_device(installer_a)
    tenant_a.is_active = False
    tenant_a.save(update_fields=["is_active"])
    assert authenticate_device(raw) is None


def test_last_seen_wird_gedrosselt(installer_a: User) -> None:
    device, _raw = _register_device(installer_a)
    assert device.last_seen is None

    touch_last_seen(device)
    device.refresh_from_db()
    first = device.last_seen
    assert first is not None

    # Innerhalb des Drosselungsfensters erfolgt kein weiterer Write.
    touch_last_seen(device)
    device.refresh_from_db()
    assert device.last_seen == first


# --- Registrierungs-Flow (anonym) --------------------------------------------------


def _make_invite(tenant: Tenant, installer: User, actor: User) -> str:
    with tenant_context(tenant):
        _invite, raw = create_invite(user=installer, actor=actor)
    return raw


def test_registrierung_zeigt_bestaetigungsseite(
    tenant_a: Tenant, installer_a: User, admin_a: User
) -> None:
    raw = _make_invite(tenant_a, installer_a, admin_a)
    response = Client().get(reverse("devices:register", args=[raw]))
    assert response.status_code == 200
    assert installer_a.full_name.encode() in response.content


def test_registrierung_unbekannter_token_ist_ungueltig() -> None:
    response = Client().get(reverse("devices:register", args=["nicht-existent"]))
    assert response.status_code == 400


def test_registrierung_legt_geraet_an_und_setzt_cookie(
    tenant_a: Tenant, installer_a: User, admin_a: User
) -> None:
    raw = _make_invite(tenant_a, installer_a, admin_a)
    client = Client()
    response = client.post(reverse("devices:register", args=[raw]), {"label": "Diensthandy"})
    assert response.status_code == 302
    assert response.url == reverse("core:dashboard")
    assert COOKIE in response.cookies
    assert Device.objects.filter(user=installer_a, label="Diensthandy").exists()
    assert AuditLog.objects.filter(action=AuditAction.DEVICE_REGISTERED).exists()


def test_einladung_kann_nicht_doppelt_eingeloest_werden(
    tenant_a: Tenant, installer_a: User, admin_a: User
) -> None:
    raw = _make_invite(tenant_a, installer_a, admin_a)
    Client().post(reverse("devices:register", args=[raw]), {"label": "Erst"})
    # Zweiter Versuch mit demselben Link schlägt fehl.
    response = Client().post(reverse("devices:register", args=[raw]), {"label": "Zweit"})
    assert response.status_code == 400
    assert Device.objects.filter(user=installer_a).count() == 1


def test_abgelaufene_einladung_ist_ungueltig(tenant_a: Tenant, installer_a: User) -> None:
    raw = generate_token()
    DeviceInvite.objects.create(
        tenant=tenant_a,
        user=installer_a,
        token_hash=hash_token(raw),
        expires_at=timezone.now() - timedelta(days=1),
    )
    response = Client().get(reverse("devices:register", args=[raw]))
    assert response.status_code == 400


def test_redeem_invite_atomar(tenant_a: Tenant, installer_a: User, admin_a: User) -> None:
    with tenant_context(tenant_a):
        invite, _raw = create_invite(user=installer_a, actor=admin_a)
        redeem_invite(invite, label="A", user_agent="pytest")
        with pytest.raises(InviteRedemptionError):
            redeem_invite(invite, label="B", user_agent="pytest")


# --- Geräteauthentifizierung per Middleware (Ende-zu-Ende) --------------------------


def test_geraet_ist_als_monteur_authentifiziert(installer_a: User, tenant_a: Tenant) -> None:
    _device, raw = _register_device(installer_a)
    with tenant_context(tenant_a):
        project = Project.objects.create(number="D-1", name="Zug", status=ProjectStatus.ACTIVE)
        ProjectAssignment.objects.create(project=project, user=installer_a)

    client = _device_client(raw)
    response = client.get(reverse("projects:list"))
    assert response.status_code == 200
    assert {p.pk for p in response.context["projects"]} == {project.pk}


def test_gesperrtes_geraet_verliert_sofort_zugriff(installer_a: User) -> None:
    device, raw = _register_device(installer_a)
    client = _device_client(raw)
    assert client.get(reverse("core:dashboard")).status_code == 200

    device.revoked_at = timezone.now()
    device.save(update_fields=["revoked_at"])
    # Nächster Request: nicht mehr authentifiziert → Weiterleitung zur Anmeldung.
    response = client.get(reverse("core:dashboard"))
    assert response.status_code == 302
    assert reverse("accounts:login") in response.url


def test_session_anmeldung_wird_nicht_von_geraet_ueberschrieben(
    admin_a: User, installer_a: User
) -> None:
    _device, raw = _register_device(installer_a)
    client = Client()
    assert client.login(username="admin-a@example.com", password="pw-admin-a-123")
    client.cookies[COOKIE] = raw  # zusätzlich ein Gerätecookie
    response = client.get(reverse("core:dashboard"))
    # Der Admin bleibt angemeldet (Session hat Vorrang); Admin sieht die Sensoren-Navigation.
    assert response.status_code == 200
    assert response.context["user"] == admin_a


# --- Verwaltung (Administratoren) --------------------------------------------------


def test_admin_erstellt_einladung_und_sieht_qr(admin_a_client: Client, installer_a: User) -> None:
    response = admin_a_client.post(
        reverse("devices:invite_create"), {"user": installer_a.pk}, follow=True
    )
    assert response.status_code == 200
    assert response.context["available"] is True
    assert response.context["qr_data_uri"].startswith("data:image/png;base64,")
    assert AuditLog.objects.filter(action=AuditAction.DEVICE_INVITE_CREATED).exists()


def test_admin_widerruft_einladung(
    admin_a_client: Client, tenant_a: Tenant, installer_a: User, admin_a: User
) -> None:
    with tenant_context(tenant_a):
        invite, raw = create_invite(user=installer_a, actor=admin_a)
    admin_a_client.post(reverse("devices:invite_revoke", args=[invite.pk]))
    assert not DeviceInvite.objects.filter(pk=invite.pk).exists()
    # Widerrufener Link funktioniert nicht mehr.
    assert Client().get(reverse("devices:register", args=[raw])).status_code == 400


def test_admin_sperrt_und_entfernt_geraet(admin_a_client: Client, installer_a: User) -> None:
    device, _raw = _register_device(installer_a)

    admin_a_client.post(reverse("devices:revoke", args=[device.pk]))
    device.refresh_from_db()
    assert device.is_revoked
    assert AuditLog.objects.filter(action=AuditAction.DEVICE_REVOKED).exists()

    admin_a_client.post(reverse("devices:remove", args=[device.pk]))
    assert not Device.objects.filter(pk=device.pk).exists()
    assert AuditLog.objects.filter(action=AuditAction.DEVICE_REMOVED).exists()


def test_admin_kann_fremdes_geraet_nicht_sperren(
    admin_a_client: Client, admin_b: User, tenant_b: Tenant
) -> None:
    foreign_installer = User.objects.create_user(
        email="monteur-b@example.com",
        password=None,
        full_name="Monteur B",
        role="installer",
        tenant=tenant_b,
    )
    device, _raw = _register_device(foreign_installer)
    assert admin_a_client.post(reverse("devices:revoke", args=[device.pk])).status_code == 404


def test_monteur_hat_keinen_zugriff_auf_geraeteverwaltung(
    installer_a: User,
) -> None:
    _device, raw = _register_device(installer_a)
    client = _device_client(raw)
    assert client.get(reverse("devices:list")).status_code == 403


def test_superadmin_muss_mandanten_waehlen(superadmin_client: Client) -> None:
    response = superadmin_client.get(reverse("devices:invite_create"))
    assert response.status_code == 302
    assert response.url == reverse("devices:list")
