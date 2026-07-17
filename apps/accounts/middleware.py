"""Middleware zur Geräteauthentifizierung von Monteuren.

Läuft nach Djangos Authentifizierungs-Middleware und vor der Mandanten-Middleware. Ist noch
kein Benutzer angemeldet (keine Admin-Session), wird versucht, das Gerät anhand des
Token-Cookies zu authentifizieren. Eine bestehende Session-Anmeldung wird nie überschrieben.

Wichtig: Die Geräteauthentifizierung muss auf Django-Ebene (Middleware) erfolgen und nicht
erst in einer DRF-Auth-Klasse – Letztere greift erst in ``APIView.initial()``, also nachdem
die Mandanten-Middleware bereits gelaufen ist. Nur so steht der Mandantenkontext für den
gesamten Request zur Verfügung.
"""

from __future__ import annotations

from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse

from apps.accounts.devices import authenticate_device, touch_last_seen


class DeviceTokenMiddleware:
    """Authentifiziert Monteur-Geräte über das langlebige Token-Cookie."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if not request.user.is_authenticated:
            token = request.COOKIES.get(settings.DEVICE_TOKEN_COOKIE_NAME)
            if token:
                device = authenticate_device(token)
                if device is not None:
                    request.user = device.user
                    request.device = device  # type: ignore[attr-defined]
                    touch_last_seen(device)
        return self.get_response(request)
