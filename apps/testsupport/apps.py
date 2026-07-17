"""AppConfig der Test-Support-App.

Diese App wird ausschließlich unter den Test-Einstellungen
(``config.settings.test``) geladen und enthält Hilfsmodelle, mit denen die abstrakte
Mandanten-Basisklasse geprüft wird. Sie ist niemals Teil der Entwicklungs- oder
Produktionskonfiguration.
"""

from __future__ import annotations

from django.apps import AppConfig


class TestSupportConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.testsupport"
    verbose_name = "Test-Unterstützung"
