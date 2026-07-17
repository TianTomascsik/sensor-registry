"""URL-Konfiguration der REST-API (gemountet unter ``/api/v1/``)."""

from __future__ import annotations

from django.urls import path

from apps.installations import api

app_name = "api"

urlpatterns = [
    path("installations/", api.InstallationCreateAPIView.as_view(), name="installation_create"),
    path("installations/list/", api.InstallationListAPIView.as_view(), name="installation_list"),
    path("installations/map/", api.MapInstallationsAPIView.as_view(), name="installation_map"),
    path(
        "installations/<uuid:installation_uuid>/photos/",
        api.InstallationPhotoAPIView.as_view(),
        name="installation_photos",
    ),
]
