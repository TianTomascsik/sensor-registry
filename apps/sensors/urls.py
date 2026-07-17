"""URL-Konfiguration der Sensoren-App."""

from __future__ import annotations

from django.urls import path

from apps.sensors import views

app_name = "sensors"

urlpatterns = [
    path("", views.SensorListView.as_view(), name="list"),
    path("neu/", views.SensorCreateView.as_view(), name="create"),
    path("import/", views.SensorImportView.as_view(), name="import"),
    path("<int:pk>/bearbeiten/", views.SensorUpdateView.as_view(), name="update"),
    path("<int:pk>/loeschen/", views.SensorDeleteView.as_view(), name="delete"),
]
