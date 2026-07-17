"""DRF-Authentifizierungsklasse für Monteur-Geräte.

Während die :class:`apps.accounts.middleware.DeviceTokenMiddleware` ``request.user`` früh
setzt (damit der Mandantenkontext gebildet werden kann), authentifiziert das REST-Framework
seine Requests eigenständig neu. Diese Klasse liefert der DRF-Ebene denselben geräte-
authentifizierten Benutzer und erzwingt – wie ``SessionAuthentication`` – bei unsicheren
Methoden eine CSRF-Prüfung (Cookie-basierte Authentifizierung ist andernfalls CSRF-anfällig).
"""

from __future__ import annotations

from django.conf import settings
from rest_framework.authentication import BaseAuthentication, SessionAuthentication
from rest_framework.request import Request

from apps.accounts.devices import authenticate_device
from apps.accounts.models import Device, User


class DeviceTokenAuthentication(BaseAuthentication):
    """Authentifiziert per Gerätetoken-Cookie inkl. CSRF-Erzwingung."""

    def authenticate(self, request: Request) -> tuple[User, Device] | None:
        token = request.COOKIES.get(settings.DEVICE_TOKEN_COOKIE_NAME)
        if not token:
            return None
        device = authenticate_device(token)
        if device is None:
            return None
        # CSRF-Prüfung analog SessionAuthentication (bei sicheren Methoden ein No-op).
        SessionAuthentication().enforce_csrf(request)
        return device.user, device
