"""Wurzel-URL-Konfiguration.

Der Django-Admin ist bewusst deaktiviert (siehe Architekturentscheidung: alle Rollen
nutzen dieselbe Bootstrap-Oberfläche). Die App-spezifischen URLs werden aus den
jeweiligen Apps eingebunden.
"""

from __future__ import annotations

from django.urls import include, path

urlpatterns = [
    path("", include("apps.pwa.urls")),
    path("", include("apps.core.urls")),
    path("konten/", include("apps.accounts.urls")),
    path("geraete/", include("apps.accounts.device_urls")),
    path("projekte/", include("apps.projects.urls")),
    path("sensoren/", include("apps.sensors.urls")),
    path("installationen/", include("apps.installations.urls")),
    path("api/v1/", include("apps.installations.api_urls")),
]
