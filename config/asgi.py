"""ASGI-Einstiegspunkt (für asynchrone Server; Basis für spätere Erweiterungen)."""

from __future__ import annotations

import os

from django.core.asgi import get_asgi_application

_env = os.environ.get("DJANGO_ENV", "prod")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", f"config.settings.{_env}")

application = get_asgi_application()
