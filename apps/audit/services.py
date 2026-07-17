"""Service-Layer für das Audit-Log.

Sämtliche Protokolleinträge entstehen über :func:`record` – bewusst als expliziter Aufruf
statt automatischer Middleware-Magie, damit jedes Ereignis nachvollziehbar und testbar an
genau einer Stelle im Code ausgelöst wird.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.http import HttpRequest

from apps.audit.models import AuditLog

if TYPE_CHECKING:
    from apps.accounts.models import User
    from apps.core.models import Tenant


def client_ip(request: HttpRequest) -> str | None:
    """Ermittelt die Client-IP.

    Berücksichtigt ``X-Forwarded-For`` (erster Eintrag = ursprünglicher Client), da die
    Anwendung in Produktion hinter dem Nginx-Reverse-Proxy läuft.
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def user_agent(request: HttpRequest) -> str:
    """Gibt den (auf Feldlänge gekürzten) User-Agent-Header zurück."""
    return request.META.get("HTTP_USER_AGENT", "")[:400]


def record(
    action: str,
    *,
    actor: User | None = None,
    tenant: Tenant | None = None,
    obj: Any | None = None,
    changes: dict[str, Any] | None = None,
    request: HttpRequest | None = None,
) -> AuditLog:
    """Schreibt einen Audit-Eintrag.

    :param action: Wert aus :class:`apps.audit.models.AuditAction`.
    :param actor: auslösender Benutzer (``None`` bei anonymen Ereignissen).
    :param tenant: betroffener Mandant; wird andernfalls aus ``actor``/``obj`` abgeleitet.
    :param obj: betroffenes Objekt; Typ, ID und Bezeichnung werden protokolliert.
    :param changes: strukturierte Vorher/Nachher-Werte.
    :param request: optionaler Request zur Erfassung von IP und User-Agent.
    """
    if tenant is None:
        tenant = _tenant_from(actor) or _tenant_from(obj)

    object_type = ""
    object_id = ""
    object_repr = ""
    if obj is not None:
        object_type = obj.__class__.__name__
        object_id = str(getattr(obj, "pk", "") or "")
        object_repr = str(obj)[:255]

    return AuditLog.objects.create(
        action=action,
        actor=actor,
        tenant=tenant,
        object_type=object_type,
        object_id=object_id,
        object_repr=object_repr,
        changes=changes or {},
        ip_address=client_ip(request) if request is not None else None,
        user_agent=user_agent(request) if request is not None else "",
    )


def _tenant_from(source: Any | None) -> Tenant | None:
    """Ermittelt den zugehörigen Mandanten einer Quelle (Benutzer oder Objekt).

    * Ist die Quelle selbst ein Mandant, wird sie direkt zurückgegeben.
    * Andernfalls wird ein vorhandenes ``tenant``-Attribut ausgewertet (ohne ein
      DB-Nachladen zu erzwingen).
    """
    from apps.core.models import Tenant as TenantModel_

    if source is None:
        return None
    if isinstance(source, TenantModel_):
        return source
    if getattr(source, "tenant_id", None) is not None:
        return source.tenant
    return None
