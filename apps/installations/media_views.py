"""Geschützte Auslieferung von Installationsfotos.

Fotos sind niemals öffentlich erreichbar. Jeder Zugriff prüft, ob der angemeldete Benutzer
die zugehörige Installation sehen darf (Mandant + für Monteure zugewiesenes Projekt).
Anschließend liefert Django die Datei in der Entwicklung direkt (``FileResponse``) und in
Produktion effizient über einen internen Nginx-Redirect (``X-Accel-Redirect``).
"""

from __future__ import annotations

import uuid
from urllib.parse import quote

from django.conf import settings
from django.db.models.fields.files import FieldFile
from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseBase,
)
from django.views import View

from apps.core.permissions import AuthenticatedViewMixin
from apps.installations.models import InstallationPhoto
from apps.installations.services import visible_installations

# Unveränderliche Fotos: eine Woche privat cachebar (entlastet Galerie und Karte).
_CACHE_CONTROL = "private, max-age=604800, immutable"


class ProtectedMediaView(AuthenticatedViewMixin, View):
    """Liefert ein Foto (Variante ``original`` oder ``thumb``) nach Berechtigungsprüfung."""

    def get(self, request: HttpRequest, photo_uuid: uuid.UUID, variant: str) -> HttpResponseBase:
        try:
            photo = InstallationPhoto.objects.select_related("installation").get(
                photo_uuid=photo_uuid
            )
        except InstallationPhoto.DoesNotExist as exc:
            raise Http404("Foto nicht gefunden.") from exc

        # Sichtbarkeit der zugehörigen Installation prüfen (Mandant + Projektzuweisung).
        if not visible_installations(self.acting_user).filter(pk=photo.installation_id).exists():
            raise Http404("Foto nicht gefunden.")

        file_field = photo.original if variant == "original" else photo.thumbnail
        return self._serve(file_field)

    @staticmethod
    def _serve(file_field: FieldFile) -> HttpResponseBase:
        response: HttpResponseBase
        if settings.MEDIA_SERVE_BACKEND == "accel":
            # Nginx liefert die Datei aus der internen Location aus.
            response = HttpResponse(content_type="image/jpeg")
            internal = settings.MEDIA_ACCEL_LOCATION.rstrip("/") + "/" + file_field.name
            response["X-Accel-Redirect"] = quote(internal)
        else:
            response = FileResponse(file_field.open("rb"), content_type="image/jpeg")
        response["Cache-Control"] = _CACHE_CONTROL
        return response
