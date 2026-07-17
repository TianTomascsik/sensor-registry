"""Views der Exporte: Projektexport und Export der Suchergebnisse.

Exporte stehen Administratoren (Superadmin, Mandantenadministrator) offen und werden
auditiert. Das Format wird über den Query-Parameter ``?format=`` gewählt.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from django.http import Http404, HttpRequest, HttpResponse
from django.utils import timezone
from django.utils.text import slugify
from django.views import View

from apps.core.permissions import AdminRequiredMixin
from apps.exports.formats import ExportFile
from apps.exports.services import FORMATS, export_installations
from apps.installations import services as installation_services
from apps.projects.models import Project
from apps.projects.services import get_visible_project


def _requested_format(request: HttpRequest) -> str:
    fmt = request.GET.get("format", "")
    if fmt not in FORMATS:
        raise Http404("Unbekanntes Exportformat.")
    return fmt


def _download(export_file: ExportFile, base_name: str) -> HttpResponse:
    response = HttpResponse(export_file.content, content_type=export_file.content_type)
    filename = f"{slugify(base_name) or 'export'}.{export_file.extension}"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _to_int(value: str | None) -> int | None:
    try:
        return int(value) if value else None
    except (TypeError, ValueError):
        return None


def _parse_date(value: str | None, at: time) -> datetime | None:
    if not value:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return timezone.make_aware(datetime.combine(parsed, at))


class ProjectExportView(AdminRequiredMixin, View):
    """Exportiert alle Installationen eines Projekts."""

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        fmt = _requested_format(request)
        try:
            project = get_visible_project(self.acting_user, pk)
        except Project.DoesNotExist as exc:
            raise Http404("Projekt nicht gefunden.") from exc
        installations = installation_services.visible_installations(self.acting_user).filter(
            project=project
        )
        export_file = export_installations(
            installations,
            fmt,
            title=f"Projekt {project.number} – {project.name}",
            actor=self.acting_user,
            request=request,
        )
        return _download(export_file, f"projekt-{project.number}")


class SearchExportView(AdminRequiredMixin, View):
    """Exportiert die aktuell gefilterten Installationen (dieselben Filter wie die Suche)."""

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        fmt = _requested_format(request)
        params = request.GET
        installations = installation_services.search_installations(
            self.acting_user,
            search=params.get("q", ""),
            deveui=params.get("deveui", ""),
            project_id=_to_int(params.get("project")),
            installer_id=_to_int(params.get("installer")),
            date_from=_parse_date(params.get("date_from"), time.min),
            date_to=_parse_date(params.get("date_to"), time.max),
        )
        export_file = export_installations(
            installations,
            fmt,
            title="Installationen",
            actor=self.acting_user,
            request=request,
        )
        return _download(export_file, "installationen")
