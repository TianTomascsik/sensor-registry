"""AppConfig der Sensoren-App."""

from __future__ import annotations

from django.apps import AppConfig


class SensorsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.sensors"
    verbose_name = "Sensoren"
