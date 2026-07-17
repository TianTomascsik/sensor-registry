"""URL-Konfiguration der Installationen-App (server-gerenderte Ansichten)."""

from __future__ import annotations

from django.urls import path

from apps.installations import views
from apps.installations.media_views import ProtectedMediaView

app_name = "installations"

urlpatterns = [
    path("", views.InstallationListView.as_view(), name="list"),
    path("karte/", views.InstallationMapView.as_view(), name="map"),
    path("suche/", views.InstallationSearchView.as_view(), name="search"),
    path("erfassen/", views.InstallationCaptureView.as_view(), name="capture"),
    path("<int:pk>/", views.InstallationDetailView.as_view(), name="detail"),
    path("<int:pk>/korrigieren/", views.InstallationCorrectView.as_view(), name="correct"),
    path("<int:pk>/stornieren/", views.InstallationCancelView.as_view(), name="cancel"),
    path(
        "medien/<uuid:photo_uuid>/<str:variant>/",
        ProtectedMediaView.as_view(),
        name="media",
    ),
]
