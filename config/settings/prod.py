"""Produktionskonfiguration.

Erzwingt sichere Voreinstellungen. Sicherheitsrelevante HTTPS-Optionen werden über
``DJANGO_SECURE_SSL`` aktiviert, sobald die Anwendung ausschließlich über HTTPS
erreichbar ist (typischerweise hinter dem Nginx-Reverse-Proxy).
"""

from __future__ import annotations

from .base import *  # noqa: F403
from .base import env

DEBUG = False

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# HTTPS-Härtung. In Produktion terminiert Nginx TLS und setzt den Weiterleitungs-Header.
_secure_ssl = env.bool("DJANGO_SECURE_SSL", default=True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = _secure_ssl
SESSION_COOKIE_SECURE = _secure_ssl
CSRF_COOKIE_SECURE = _secure_ssl
SECURE_HSTS_SECONDS = 31536000 if _secure_ssl else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = _secure_ssl
SECURE_HSTS_PRELOAD = _secure_ssl

# Zusätzliche Sicherheits-Header (ergänzend zu jenen, die Nginx setzt).
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# In Produktion liefert Nginx geschützte Medien via X-Accel-Redirect aus.
MEDIA_SERVE_BACKEND = env("MEDIA_SERVE_BACKEND", default="accel")

# __Host-Präfix härtet das Gerätetoken-Cookie (nur über HTTPS, Path=/, ohne Domain-Attribut).
# Setzt DJANGO_SECURE_SSL=1 voraus, damit das Cookie mit Secure ausgeliefert wird.
if _secure_ssl:
    DEVICE_TOKEN_COOKIE_NAME = "__Host-device_token"
