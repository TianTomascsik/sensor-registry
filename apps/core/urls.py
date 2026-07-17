"""URL-Konfiguration der Kern-App."""

from __future__ import annotations

from django.urls import path

from apps.core import views

app_name = "core"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("mandanten/", views.TenantListView.as_view(), name="tenant_list"),
    path("mandanten/neu/", views.TenantCreateView.as_view(), name="tenant_create"),
    path("mandanten/<int:pk>/bearbeiten/", views.TenantUpdateView.as_view(), name="tenant_update"),
    path(
        "mandanten/<int:pk>/status/",
        views.TenantToggleActiveView.as_view(),
        name="tenant_toggle_active",
    ),
    path("mandant-wechseln/", views.TenantSwitchView.as_view(), name="tenant_switch"),
]
