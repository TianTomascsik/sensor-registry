"""URL-Konfiguration der PWA (im Root gemountet, damit /sw.js Root-Scope hat)."""

from __future__ import annotations

from django.urls import path

from apps.pwa import views

urlpatterns = [
    path("sw.js", views.service_worker, name="service_worker"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
]
