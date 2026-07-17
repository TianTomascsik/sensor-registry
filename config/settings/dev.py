"""Entwicklungskonfiguration.

Aktiviert Debug-Ausgaben und lockert sicherheitsrelevante Cookie-Flags, damit die
Anwendung ohne HTTPS lokal betrieben werden kann. NICHT in Produktion verwenden.
"""

from __future__ import annotations

from .base import *  # noqa: F403
from .base import STORAGES, env

DEBUG = True

# In Entwicklung/Tests ohne vorherigen collectstatic-Lauf: einfacher Static-Storage ohne
# Hash-Manifest. Das Manifest (ManifestStaticFilesStorage) bleibt der Produktion vorbehalten.
STORAGES = {
    **STORAGES,
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS",
    default=["localhost", "127.0.0.1", "0.0.0.0"],
)

# Ohne HTTPS dürfen die Cookies nicht als "Secure" markiert sein, sonst werden sie
# vom Browser nie gesendet.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

INTERNAL_IPS = ["127.0.0.1"]

# Django-Standard-Passwort-Hasher ist bewusst langsam. Für Tests beschleunigt der
# MD5-Hasher die Ausführung erheblich, ohne Produktionssicherheit zu berühren.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
