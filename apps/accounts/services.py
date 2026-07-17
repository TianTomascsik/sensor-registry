"""Service-Layer der Accounts-App: Benutzerverwaltung.

Kapselt das Anlegen, Ändern und (De-)Aktivieren von Benutzern inklusive
Audit-Protokollierung. Die Sichtbarkeit richtet sich nach dem aktiven Mandantenkontext:
Mandantenadmins sehen ausschließlich Benutzer des eigenen Mandanten, Superadmins je nach
gewähltem Mandanten alle oder die des gewählten Mandanten.
"""

from __future__ import annotations

from django.db.models import QuerySet
from django.http import HttpRequest

from apps.accounts.models import Role, User
from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.core.models import Tenant
from apps.core.tenancy import current_tenant_or_none


def list_users() -> QuerySet[User]:
    """Benutzer im Rahmen des aktiven Mandantenkontexts.

    Im Systemkontext (Superadmin ohne Mandantenauswahl) werden alle Benutzer geliefert,
    andernfalls nur die des aktiven Mandanten.
    """
    scope = current_tenant_or_none()
    qs = User.objects.select_related("tenant")
    if scope is not None:
        qs = qs.filter(tenant=scope)
    return qs.order_by("full_name")


def get_managed_user(pk: int) -> User:
    """Lädt einen im aktuellen Kontext verwaltbaren Benutzer (sonst ``DoesNotExist``)."""
    return list_users().get(pk=pk)


def create_user(
    *,
    tenant: Tenant,
    email: str,
    full_name: str,
    role: str,
    password: str | None,
    actor: User,
    request: HttpRequest | None = None,
) -> User:
    """Legt einen Benutzer innerhalb eines Mandanten an.

    Für Monteure ohne Passwort wird ein unbenutzbares Passwort gesetzt; ihr Zugang erfolgt
    später über die Geräteanmeldung (QR/Einladung).
    """
    user = User.objects.create_user(
        email=email,
        password=password or None,
        full_name=full_name,
        role=role,
        tenant=tenant,
    )
    record(
        AuditAction.USER_CREATED,
        actor=actor,
        tenant=tenant,
        obj=user,
        changes={"email": email, "full_name": full_name, "role": role},
        request=request,
    )
    return user


def update_user(
    user: User,
    *,
    full_name: str,
    role: str,
    actor: User,
    request: HttpRequest | None = None,
) -> User:
    """Aktualisiert Name und Rolle eines Benutzers."""
    changes: dict[str, dict[str, object]] = {}
    if user.full_name != full_name:
        changes["full_name"] = {"von": user.full_name, "zu": full_name}
    if user.role != role:
        changes["role"] = {"von": user.role, "zu": role}
    user.full_name = full_name
    user.role = role
    user.save(update_fields=["full_name", "role"])
    if changes:
        record(
            AuditAction.USER_UPDATED,
            actor=actor,
            tenant=user.tenant,
            obj=user,
            changes=changes,
            request=request,
        )
    return user


def set_user_active(
    user: User,
    *,
    active: bool,
    actor: User,
    request: HttpRequest | None = None,
) -> User:
    """Aktiviert bzw. deaktiviert einen Benutzer."""
    if user.is_active == active:
        return user
    user.is_active = active
    user.save(update_fields=["is_active"])
    record(
        AuditAction.USER_ACTIVATED if active else AuditAction.USER_DEACTIVATED,
        actor=actor,
        tenant=user.tenant,
        obj=user,
        request=request,
    )
    return user


def assignable_roles(actor: User) -> list[tuple[str, str]]:
    """Rollen, die der handelnde Benutzer vergeben darf.

    Superadmins wie Mandantenadmins verwalten innerhalb eines Mandanten die Rollen
    Mandantenadministrator und Monteur. Superadmins selbst werden per
    ``manage.py createsuperuser`` angelegt.
    """
    return [
        (Role.TENANT_ADMIN.value, Role.TENANT_ADMIN.label),
        (Role.INSTALLER.value, Role.INSTALLER.label),
    ]
