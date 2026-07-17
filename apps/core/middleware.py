"""Middleware, die den Mandantenkontext pro Request etabliert und aufräumt.

Läuft **nach** der Authentifizierung (siehe Reihenfolge in ``settings.MIDDLEWARE``) und
leitet den aktiven Mandanten aus dem angemeldeten Benutzer ab:

* Nicht angemeldet          → kein Kontext (fail-closed; Login-Seite berührt keine
  mandantengebundenen Daten).
* Superadmin                → gewählter Mandant aus der Session, sonst Systemkontext
  (mandantenübergreifende Gesamtsicht).
* Mandantenadmin / Monteur  → fest der eigene Mandant.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager

from django.http import HttpRequest, HttpResponse

from apps.core.models import Tenant
from apps.core.tenancy import system_context, tenant_context

#: Session-Schlüssel, unter dem der vom Superadmin gewählte Mandant abgelegt wird.
ACTIVE_TENANT_SESSION_KEY = "active_tenant_id"


class TenantContextMiddleware:
    """Setzt für die Dauer des Requests den passenden Mandantenkontext."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        context = self._context_for(request)
        if context is None:
            return self.get_response(request)
        with context:
            return self.get_response(request)

    def _context_for(self, request: HttpRequest) -> AbstractContextManager[object] | None:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None

        if user.is_superadmin:
            active = self._selected_tenant(request)
            if active is not None:
                return tenant_context(active)
            return system_context()

        # Mandantenadmin/Monteur: immer der eigene Mandant. Fehlt dieser (Datenfehler),
        # bleibt der Kontext ungesetzt und der Zugriff schlägt fail-closed fehl.
        if user.tenant_id is None:
            return None
        return tenant_context(user.tenant)

    @staticmethod
    def _selected_tenant(request: HttpRequest) -> Tenant | None:
        """Lädt den vom Superadmin per Umschalter gewählten Mandanten aus der Session."""
        tenant_id = request.session.get(ACTIVE_TENANT_SESSION_KEY)
        if not tenant_id:
            return None
        # Tenant ist nicht mandantengebunden und daher ohne Kontext abfragbar.
        return Tenant.objects.filter(pk=tenant_id, is_active=True).first()
