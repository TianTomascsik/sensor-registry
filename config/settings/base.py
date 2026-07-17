"""Basiskonfiguration, geteilt von allen Umgebungen.

Umgebungsspezifische Werte werden ausschließlich über Umgebungsvariablen (bzw. eine
``.env``-Datei im Projektwurzelverzeichnis) eingelesen. Die Module ``dev`` und ``prod``
importieren diese Basis und überschreiben nur, was sich tatsächlich unterscheidet.
"""

from __future__ import annotations

from pathlib import Path

import django_stubs_ext
import environ

# Macht generische Class-Based-Views (ListView[User], FormView[MyForm]) zur Laufzeit
# subscriptbar, damit die Typannotationen mit dem Laufzeitverhalten übereinstimmen.
django_stubs_ext.monkeypatch()

# BASE_DIR zeigt auf das Projektwurzelverzeichnis (drei Ebenen über dieser Datei:
# config/settings/base.py -> config/settings -> config -> <root>).
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

# --- Sicherheit / Kern ---
SECRET_KEY: str = env("DJANGO_SECRET_KEY", default="unsafe-dev-key-change-me")
DEBUG: bool = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS: list[str] = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# --- Anwendungen ---
DJANGO_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
]
THIRD_PARTY_APPS = [
    "rest_framework",
]
LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.audit",
    "apps.projects",
    "apps.sensors",
    "apps.installations",
    "apps.pwa",
    "apps.exports",
]
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Nach der Authentifizierung: authentifiziert Monteur-Geräte per Token-Cookie, sofern
    # keine Session-Anmeldung vorliegt (setzt request.user, ohne eine Admin-Session zu
    # überschreiben). Muss VOR der Mandanten-Middleware laufen, damit der Mandantenkontext
    # aus dem Geräte-Benutzer abgeleitet werden kann.
    "apps.accounts.middleware.DeviceTokenMiddleware",
    # Muss NACH der Authentifizierung laufen: leitet den Mandantenkontext aus dem
    # angemeldeten Benutzer ab und räumt ihn am Ende jedes Requests wieder auf.
    "apps.core.middleware.TenantContextMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.app_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Bootstrap kennt "danger" statt "error"; Django-Nachrichten entsprechend abbilden.
from django.contrib.messages import constants as message_constants  # noqa: E402

MESSAGE_TAGS = {message_constants.ERROR: "danger"}

# --- Datenbank ---
DATABASES = {
    "default": {
        **env.db("DATABASE_URL", default="postgres://papa:papa@127.0.0.1:5432/papa"),
        "ATOMIC_REQUESTS": True,
        # Die Anwendung nutzt keine TransactionTestCase mit serialized_rollback; die
        # (langsame) Serialisierung der Ausgangsdaten beim Test-Setup ist daher unnötig.
        "TEST": {"SERIALIZE": False},
    }
}

# --- Authentifizierung ---
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["apps.accounts.backends.EmailBackend"]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Internationalisierung ---
LANGUAGE_CODE = "de"
TIME_ZONE = "Europe/Zurich"
USE_I18N = False
USE_TZ = True

# --- Statische Dateien / Medien ---
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Auslieferung geschützter Medien: "django" (direkt) oder "accel" (X-Accel-Redirect via Nginx).
MEDIA_SERVE_BACKEND = env("MEDIA_SERVE_BACKEND", default="django")
MEDIA_ACCEL_LOCATION = env("MEDIA_ACCEL_LOCATION", default="/_protected_media/")

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Sessions / CSRF-Cookies ---
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
# Die PWA liest das CSRF-Token zur Laufzeit aus dem Cookie, daher ist es nicht HttpOnly.
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"

# --- Upload-Grenzen (auf die Bild-Pipeline abgestimmt) ---
# 15 MB pro Datei; darüber wird der Upload abgelehnt, bevor Pillow ihn verarbeitet.
DATA_UPLOAD_MAX_MEMORY_SIZE = 15 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 15 * 1024 * 1024
# Schutz vor Parameter-Flut (z. B. große Formulare/Sync-Payloads).
DATA_UPLOAD_MAX_NUMBER_FIELDS = 2000

# --- Django REST Framework ---
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "apps.accounts.authentication.DeviceTokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "login": "10/min",
        "sync": "120/min",
    },
    "UNAUTHENTICATED_USER": None,
}

# --- Fachliche Standardwerte ---
# Standard-Grenzwert für die GPS-Genauigkeit (Meter); pro Mandant überschreibbar.
GPS_ACCURACY_DEFAULT_THRESHOLD_M = 5

# --- Geräteanmeldung (Monteure) ---
# Cookie-Name des Gerätetokens. In Produktion wird der __Host-Präfix verwendet (siehe prod.py),
# der Secure + Path=/ + kein Domain-Attribut voraussetzt.
DEVICE_TOKEN_COOKIE_NAME = "device_token"
# Lebensdauer des Gerätetokens (~1 Jahr): „dauerhaft angemeldet“ ohne Passwort.
DEVICE_TOKEN_COOKIE_MAX_AGE = 365 * 24 * 3600
# Gültigkeitsdauer einer Einladung in Tagen.
DEVICE_INVITE_TTL_DAYS = 14
# „last_seen“ wird höchstens einmal je Zeitfenster (Sekunden) aktualisiert – verhindert
# einen Datenbank-Write pro Request.
DEVICE_LAST_SEEN_THROTTLE_SECONDS = 900

# --- Logging ---
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} [{levelname}] {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "apps": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}
