"""URL-Konfiguration der Projekte-App."""

from __future__ import annotations

from django.urls import path

from apps.projects import views

app_name = "projects"

urlpatterns = [
    path("", views.ProjectListView.as_view(), name="list"),
    path("neu/", views.ProjectCreateView.as_view(), name="create"),
    path("<int:pk>/", views.ProjectDetailView.as_view(), name="detail"),
    path("<int:pk>/bearbeiten/", views.ProjectUpdateView.as_view(), name="update"),
    path("<int:pk>/zuweisen/", views.ProjectAssignView.as_view(), name="assign"),
    path(
        "<int:pk>/zuweisung/<int:user_id>/entfernen/",
        views.ProjectUnassignView.as_view(),
        name="unassign",
    ),
]
