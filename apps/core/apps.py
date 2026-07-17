"""AppConfig der Kern-App."""

from __future__ import annotations

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Kern"

    def ready(self) -> None:
        # Registriert den Mandanten-System-Check (Import mit Seiteneffekt).
        from apps.core import checks  # noqa: F401
