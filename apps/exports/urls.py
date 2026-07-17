"""URL-Konfiguration der Exporte."""

from __future__ import annotations

from django.urls import path

from apps.exports import views

app_name = "exports"

urlpatterns = [
    path("projekt/<int:pk>/", views.ProjectExportView.as_view(), name="project"),
    path("suche/", views.SearchExportView.as_view(), name="search"),
]
