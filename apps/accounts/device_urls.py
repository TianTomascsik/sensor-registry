"""URL-Konfiguration der Geräteanmeldung (mandantenübergreifend gemountet unter /geraete/)."""

from __future__ import annotations

from django.urls import path

from apps.accounts import device_views as views

app_name = "devices"

urlpatterns = [
    path("", views.DeviceListView.as_view(), name="list"),
    path("einladung/neu/", views.InviteCreateView.as_view(), name="invite_create"),
    path("einladung/anzeigen/", views.InviteShowView.as_view(), name="invite_show"),
    path("einladung/<int:pk>/widerrufen/", views.InviteRevokeView.as_view(), name="invite_revoke"),
    path("<int:pk>/sperren/", views.DeviceRevokeView.as_view(), name="revoke"),
    path("<int:pk>/entfernen/", views.DeviceRemoveView.as_view(), name="remove"),
    path("registrieren/<str:token>/", views.DeviceRegisterView.as_view(), name="register"),
]
