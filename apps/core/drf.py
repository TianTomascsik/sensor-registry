"""DRF-Ausnahmebehandlung für den fail-closed Mandantenkontext.

Ein mandantenübergreifender Benutzer (Superadmin ohne gewählten Mandanten) läuft im
System-/kontextlosen Zustand. Lesende Zugriffe sind dort erlaubt, ein mandantengebundener
Schreibvorgang hat jedoch keinen Mandanten zum Zuordnen und wirft :class:`TenantContextMissing`.
Ohne Sonderbehandlung würde daraus ein HTTP 500 – dieser Handler übersetzt den vorhersehbaren
Zustand in eine klare 409-Antwort. Alle übrigen Ausnahmen behandelt DRF unverändert.
"""

from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_handler

from apps.core.tenancy import TenantContextMissing


def tenant_aware_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Übersetzt fehlenden Mandantenkontext in eine 409-Antwort, sonst DRF-Standard."""
    if isinstance(exc, TenantContextMissing):
        return Response(
            {"detail": "Kein Mandant aktiv. Bitte zuerst einen Mandanten wählen."},
            status=status.HTTP_409_CONFLICT,
        )
    return drf_default_handler(exc, context)
