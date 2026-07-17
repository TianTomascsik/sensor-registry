"""Service-Layer der Kern-App: Mandantenverwaltung.

Sämtliche schreibenden Operationen auf Mandanten laufen über diese Funktionen. Sie kapseln
die Geschäftslogik (inkl. Audit-Protokollierung) und halten die Views schlank.
"""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet
from django.http import HttpRequest

from apps.accounts.models import User
from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.core.models import Tenant


def diff_fields(instance: Any, new_values: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Berechnet Vorher/Nachher-Werte für die geänderten Felder.

    Gibt ein Mapping ``{feldname: {"von": alt, "zu": neu}}`` zurück – nur für Felder, deren
    Wert sich tatsächlich ändert. Grundlage für revisionssichere Audit-Einträge.
    """
    changes: dict[str, dict[str, Any]] = {}
    for field, new in new_values.items():
        old = getattr(instance, field)
        if old != new:
            changes[field] = {"von": _jsonable(old), "zu": _jsonable(new)}
    return changes


def _jsonable(value: Any) -> Any:
    """Wandelt Werte in JSON-serialisierbare Form (für das ``changes``-Feld)."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


def list_tenants() -> QuerySet[Tenant]:
    """Alle Mandanten (nur für Superadmins)."""
    return Tenant.objects.all()


def create_tenant(
    *,
    name: str,
    slug: str,
    gps_accuracy_threshold_m: int,
    actor: User,
    request: HttpRequest | None = None,
) -> Tenant:
    """Legt einen neuen Mandanten an und protokolliert die Aktion."""
    tenant = Tenant.objects.create(
        name=name,
        slug=slug,
        gps_accuracy_threshold_m=gps_accuracy_threshold_m,
    )
    record(
        AuditAction.TENANT_CREATED,
        actor=actor,
        tenant=tenant,
        obj=tenant,
        changes={
            "name": name,
            "slug": slug,
            "gps_accuracy_threshold_m": gps_accuracy_threshold_m,
        },
        request=request,
    )
    return tenant


def update_tenant(
    tenant: Tenant,
    *,
    name: str,
    gps_accuracy_threshold_m: int,
    actor: User,
    request: HttpRequest | None = None,
) -> Tenant:
    """Aktualisiert Stammdaten eines Mandanten (Kürzel bleibt unveränderlich)."""
    changes = diff_fields(
        tenant,
        {"name": name, "gps_accuracy_threshold_m": gps_accuracy_threshold_m},
    )
    tenant.name = name
    tenant.gps_accuracy_threshold_m = gps_accuracy_threshold_m
    tenant.save(update_fields=["name", "gps_accuracy_threshold_m"])
    if changes:
        record(
            AuditAction.TENANT_UPDATED,
            actor=actor,
            tenant=tenant,
            obj=tenant,
            changes=changes,
            request=request,
        )
    return tenant


def set_tenant_active(
    tenant: Tenant,
    *,
    active: bool,
    actor: User,
    request: HttpRequest | None = None,
) -> Tenant:
    """Aktiviert bzw. deaktiviert einen Mandanten.

    Ein deaktivierter Mandant sperrt die Anmeldung all seiner Benutzer (siehe
    :class:`apps.accounts.backends.EmailBackend`).
    """
    if tenant.is_active == active:
        return tenant
    tenant.is_active = active
    tenant.save(update_fields=["is_active"])
    record(
        AuditAction.TENANT_ACTIVATED if active else AuditAction.TENANT_DEACTIVATED,
        actor=actor,
        tenant=tenant,
        obj=tenant,
        request=request,
    )
    return tenant
