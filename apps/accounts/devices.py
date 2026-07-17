"""Service-Layer der passwortlosen Geräteanmeldung für Monteure.

Ablauf:
    1. Ein Administrator erstellt eine Einladung für einen Monteur (:func:`create_invite`).
       Der Klartext-Token wird nur einmalig als Link/QR-Code ausgeliefert.
    2. Der Monteur öffnet den Link auf seinem Gerät und registriert es
       (:func:`redeem_invite`). Dabei entsteht ein dauerhafter Gerätetoken, der als
       HttpOnly-Cookie gespeichert wird; in der Datenbank liegt nur dessen Hash.
    3. Jeder weitere Request authentifiziert das Gerät anhand des Cookies
       (:func:`authenticate_device`, aufgerufen aus der Middleware).

Sämtliche Tokens werden ausschließlich als SHA-256-Hash gespeichert.
"""

from __future__ import annotations

import base64
import hashlib
import io
import secrets
from datetime import timedelta

import qrcode
from django.conf import settings
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from apps.accounts.models import Device, DeviceInvite, Role, User
from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.core.models import Tenant
from apps.core.tenancy import current_tenant_or_none


class InviteRedemptionError(RuntimeError):
    """Wird geworfen, wenn eine Einladung nicht (mehr) eingelöst werden kann."""


def generate_token() -> str:
    """Erzeugt einen kryptografisch sicheren, URL-tauglichen Token (256 Bit)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Bildet den SHA-256-Hash eines Tokens (Hexdarstellung)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- Einladungen -------------------------------------------------------------------


def create_invite(
    *, user: User, actor: User, request: HttpRequest | None = None
) -> tuple[DeviceInvite, str]:
    """Erstellt eine Einladung für einen Monteur und gibt (Einladung, Klartext-Token) zurück.

    Der Klartext-Token wird nur hier zurückgegeben und danach nie wieder verfügbar.
    """
    if user.role != Role.INSTALLER:
        raise InviteRedemptionError("Einladungen können nur für Monteure erstellt werden.")
    tenant = user.tenant
    if tenant is None:
        raise InviteRedemptionError("Der Monteur ist keinem Mandanten zugeordnet.")
    raw_token = generate_token()
    invite = DeviceInvite.objects.create(
        tenant=tenant,
        user=user,
        token_hash=hash_token(raw_token),
        created_by=actor,
        expires_at=timezone.now() + timedelta(days=settings.DEVICE_INVITE_TTL_DAYS),
    )
    record(
        AuditAction.DEVICE_INVITE_CREATED,
        actor=actor,
        tenant=tenant,
        obj=invite,
        changes={"monteur": user.email},
        request=request,
    )
    return invite, raw_token


def get_invite_by_token(token: str) -> DeviceInvite | None:
    """Sucht eine Einladung anhand des Klartext-Tokens (ohne Gültigkeitsprüfung)."""
    return (
        DeviceInvite.objects.select_related("user", "user__tenant", "tenant")
        .filter(token_hash=hash_token(token))
        .first()
    )


def redeem_invite(
    invite: DeviceInvite,
    *,
    label: str,
    user_agent: str,
    request: HttpRequest | None = None,
) -> tuple[Device, str]:
    """Löst eine Einladung atomar ein und registriert ein neues Gerät.

    Die Einlösung erfolgt über ein bedingtes UPDATE (nur wenn noch nicht benutzt und nicht
    abgelaufen). Schlägt dieses fehl, wurde die Einladung parallel bereits eingelöst oder ist
    abgelaufen – dann wird :class:`InviteRedemptionError` geworfen.
    """
    now = timezone.now()
    updated = DeviceInvite.objects.filter(
        pk=invite.pk, used_at__isnull=True, expires_at__gt=now
    ).update(used_at=now)
    if updated == 0:
        raise InviteRedemptionError(
            "Diese Einladung ist ungültig, abgelaufen oder bereits benutzt."
        )

    raw_token = generate_token()
    device = Device.objects.create(
        tenant=invite.tenant,
        user=invite.user,
        label=label,
        token_hash=hash_token(raw_token),
        user_agent=user_agent[:400],
    )
    record(
        AuditAction.DEVICE_REGISTERED,
        actor=invite.user,
        tenant=invite.tenant,
        obj=device,
        changes={"monteur": invite.user.email, "bezeichnung": label},
        request=request,
    )
    return device, raw_token


def list_pending_invites() -> QuerySet[DeviceInvite]:
    """Offene (nicht eingelöste, nicht abgelaufene) Einladungen im aktiven Mandantenkontext."""
    scope = current_tenant_or_none()
    qs = DeviceInvite.objects.select_related("user").filter(
        used_at__isnull=True, expires_at__gt=timezone.now()
    )
    if scope is not None:
        qs = qs.filter(tenant=scope)
    return qs.order_by("-created_at")


def get_managed_invite(pk: int) -> DeviceInvite:
    """Lädt eine im aktuellen Kontext verwaltbare Einladung (sonst ``DoesNotExist``)."""
    scope = current_tenant_or_none()
    qs = DeviceInvite.objects.all()
    if scope is not None:
        qs = qs.filter(tenant=scope)
    return qs.get(pk=pk)


def revoke_invite(invite: DeviceInvite, *, actor: User, request: HttpRequest | None = None) -> None:
    """Widerruft eine offene Einladung (der Link wird dadurch unbrauchbar)."""
    tenant = invite.tenant
    record(
        AuditAction.DEVICE_INVITE_REVOKED,
        actor=actor,
        tenant=tenant,
        obj=invite,
        changes={"monteur": invite.user.email},
        request=request,
    )
    invite.delete()


# --- Geräte ------------------------------------------------------------------------


def list_devices() -> QuerySet[Device]:
    """Geräte im aktiven Mandantenkontext (Superadmin ohne Auswahl: alle)."""
    scope = current_tenant_or_none()
    qs = Device.objects.select_related("user")
    if scope is not None:
        qs = qs.filter(tenant=scope)
    return qs.order_by("-created_at")


def get_managed_device(pk: int) -> Device:
    """Lädt ein im aktuellen Kontext verwaltbares Gerät (sonst ``DoesNotExist``)."""
    return list_devices().get(pk=pk)


def revoke_device(device: Device, *, actor: User, request: HttpRequest | None = None) -> None:
    """Sperrt ein Gerät. Wirkt sofort beim nächsten Request des Geräts."""
    if device.revoked_at is None:
        device.revoked_at = timezone.now()
        device.save(update_fields=["revoked_at"])
        record(
            AuditAction.DEVICE_REVOKED,
            actor=actor,
            tenant=device.tenant,
            obj=device,
            request=request,
        )


def remove_device(device: Device, *, actor: User, request: HttpRequest | None = None) -> None:
    """Entfernt ein Gerät vollständig."""
    record(
        AuditAction.DEVICE_REMOVED,
        actor=actor,
        tenant=device.tenant,
        obj=device,
        request=request,
    )
    device.delete()


# --- Authentifizierung -------------------------------------------------------------


def authenticate_device(token: str) -> Device | None:
    """Authentifiziert ein Gerät anhand des Klartext-Tokens.

    Liefert das Gerät nur, wenn es nicht gesperrt ist und der zugehörige Benutzer sowie
    dessen Mandant aktiv sind. Andernfalls ``None``.
    """
    device = (
        Device.objects.select_related("user", "user__tenant")
        .filter(token_hash=hash_token(token), revoked_at__isnull=True)
        .first()
    )
    if device is None:
        return None
    user = device.user
    if not user.is_active:
        return None
    if user.tenant is None or not user.tenant.is_active:
        return None
    return device


def touch_last_seen(device: Device) -> None:
    """Aktualisiert ``last_seen`` höchstens einmal je Drosselungsfenster (ein Write)."""
    window = timedelta(seconds=settings.DEVICE_LAST_SEEN_THROTTLE_SECONDS)
    threshold = timezone.now() - window
    if device.last_seen is None or device.last_seen < threshold:
        Device.objects.filter(pk=device.pk).update(last_seen=timezone.now())


# --- Cookie / QR -------------------------------------------------------------------


def set_device_cookie(response: HttpResponse, token: str) -> None:
    """Setzt das langlebige Gerätetoken-Cookie (HttpOnly, SameSite=Lax)."""
    response.set_cookie(
        settings.DEVICE_TOKEN_COOKIE_NAME,
        token,
        max_age=settings.DEVICE_TOKEN_COOKIE_MAX_AGE,
        secure=getattr(settings, "SESSION_COOKIE_SECURE", False),
        httponly=True,
        samesite="Lax",
        path="/",
    )


def clear_device_cookie(response: HttpResponse) -> None:
    """Entfernt das Gerätetoken-Cookie."""
    response.delete_cookie(settings.DEVICE_TOKEN_COOKIE_NAME, path="/")


def qr_png_data_uri(url: str) -> str:
    """Erzeugt einen QR-Code für ``url`` als eingebettetes PNG (data:-URI)."""
    image = qrcode.make(url)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def invite_tenant_scope() -> Tenant | None:
    """Der aktive Mandant für die Einladungs-/Geräteverwaltung (None = Gesamtsicht)."""
    return current_tenant_or_none()
