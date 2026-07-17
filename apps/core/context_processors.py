"""Template-Kontext, der auf jeder Seite verfügbar ist.

Stellt den Anwendungsnamen sowie – für Superadmins – den aktiven Mandanten und die Liste
wählbarer Mandanten für den Umschalter bereit.
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from apps.core.middleware import ACTIVE_TENANT_SESSION_KEY
from apps.core.models import Tenant

APP_NAME = "Sensor-Dokumentation"


def app_context(request: HttpRequest) -> dict[str, Any]:
    """Fügt anwendungsweite Kontextvariablen hinzu."""
    context: dict[str, Any] = {"app_name": APP_NAME}

    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return context

    if user.is_superadmin:
        active_id = request.session.get(ACTIVE_TENANT_SESSION_KEY)
        context["is_superadmin"] = True
        context["available_tenants"] = Tenant.objects.filter(is_active=True)
        context["active_tenant"] = (
            Tenant.objects.filter(pk=active_id).first() if active_id else None
        )
    else:
        context["active_tenant"] = user.tenant

    return context
