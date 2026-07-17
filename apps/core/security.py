"""Middleware für zusätzliche Sicherheits-Header (CSP und Permissions-Policy).

Djangos ``SecurityMiddleware`` setzt bereits HSTS, ``X-Content-Type-Options``,
Referrer-Policy und Cross-Origin-Opener-Policy. Diese Middleware ergänzt eine
**Content-Security-Policy** und eine **Permissions-Policy**.

Die CSP ist bewusst streng (``script-src 'self'`` – die Anwendung nutzt keine Inline-Skripte
und keine Inline-Event-Handler). Erlaubt werden lediglich Bilder als ``data:``/``blob:``
(QR-Codes, Foto-Vorschauen, eingebettete Thumbnails) sowie die OpenStreetMap-Kachelserver
für die Karte. Geolocation bleibt für die Erfassung freigegeben.
"""

from __future__ import annotations

from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse

#: CSP-Direktiven als Mapping; werden zu einem Header-Wert zusammengesetzt.
DEFAULT_CSP: dict[str, str] = {
    "default-src": "'self'",
    "script-src": "'self'",
    "style-src": "'self' 'unsafe-inline'",
    "img-src": "'self' data: blob: https://*.tile.openstreetmap.org",
    "font-src": "'self'",
    "connect-src": "'self'",
    "worker-src": "'self'",
    "manifest-src": "'self'",
    "base-uri": "'self'",
    "form-action": "'self'",
    "frame-ancestors": "'none'",
    "object-src": "'none'",
}

#: Permissions-Policy: Geolocation für die Erfassung erlauben, übrige Sensoren sperren.
DEFAULT_PERMISSIONS_POLICY = "geolocation=(self), camera=(), microphone=(), payment=()"


def _build_csp() -> str:
    directives = getattr(settings, "CONTENT_SECURITY_POLICY", DEFAULT_CSP)
    return "; ".join(f"{key} {value}" for key, value in directives.items())


class SecurityHeadersMiddleware:
    """Setzt Content-Security-Policy und Permissions-Policy auf jede Antwort."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self.csp = _build_csp()
        self.permissions_policy = getattr(
            settings, "PERMISSIONS_POLICY", DEFAULT_PERMISSIONS_POLICY
        )

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", self.csp)
        response.setdefault("Permissions-Policy", self.permissions_policy)
        return response
