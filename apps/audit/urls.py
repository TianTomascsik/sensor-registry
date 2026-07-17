"""URL-Konfiguration der Audit-Log-Ansicht."""

from __future__ import annotations

from django.urls import path

from apps.audit import views

app_name = "audit"

urlpatterns = [
    path("", views.AuditLogListView.as_view(), name="list"),
]
