"""URL-Konfiguration der Accounts-App."""

from __future__ import annotations

from django.urls import path

from apps.accounts import views

app_name = "accounts"

urlpatterns = [
    path("anmelden/", views.login_view, name="login"),
    path("abmelden/", views.logout_view, name="logout"),
    path("benutzer/", views.UserListView.as_view(), name="user_list"),
    path("benutzer/neu/", views.UserCreateView.as_view(), name="user_create"),
    path("benutzer/<int:pk>/bearbeiten/", views.UserUpdateView.as_view(), name="user_update"),
    path(
        "benutzer/<int:pk>/status/",
        views.UserToggleActiveView.as_view(),
        name="user_toggle_active",
    ),
]
