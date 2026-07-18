"""Server-gerenderte Views der Installationen-App.

Enthält den mobilen Erfassungsbildschirm (die eigentliche Logik läuft clientseitig gegen die
REST-API), die Liste und Detailansicht sowie die administrative Korrektur/Storno.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any

from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import FormView, ListView, TemplateView

from apps.accounts.models import Role, User
from apps.core.permissions import AdminRequiredMixin, AuthenticatedViewMixin
from apps.core.tenancy import current_tenant_or_none
from apps.installations import services
from apps.installations.forms import (
    InstallationCancelForm,
    InstallationCorrectForm,
    InstallationSearchForm,
)
from apps.installations.models import Installation
from apps.projects.services import visible_projects


@method_decorator(ensure_csrf_cookie, name="dispatch")
class InstallationCaptureView(AuthenticatedViewMixin, TemplateView):
    """Mobiler Erfassungsbildschirm: GPS, Fotos und Sensor-/Projektauswahl.

    Die Auswahllisten (Projekte/Sensoren) lädt der Client aus dem Offline-Replikat
    (IndexedDB); die Seite selbst enthält daher keine serverseitig gerenderten Daten und
    keinen ``{% csrf_token %}`` (das CSRF-Token wird zur Laufzeit aus dem Cookie gelesen),
    damit sie unbedenklich vom Service Worker zwischengespeichert werden kann.
    """

    template_name = "installations/capture.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        tenant = self.acting_user.tenant
        context["gps_threshold_m"] = tenant.gps_accuracy_threshold_m if tenant is not None else 5
        return context


class InstallationListView(AuthenticatedViewMixin, ListView[Installation]):
    """Liste der sichtbaren Installationen (mit Suche und Pagination)."""

    template_name = "installations/installation_list.html"
    context_object_name = "installations"
    paginate_by = 25

    def get_queryset(self) -> Any:
        self.search = self.request.GET.get("q", "")
        return services.search_installations(self.acting_user, search=self.search)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["search"] = self.search
        context["can_manage"] = self.acting_user.can_manage_users
        return context


class InstallationMapView(AuthenticatedViewMixin, TemplateView):
    """Kartenansicht der aktiven Installationen (Leaflet). Die Daten lädt das Skript."""

    template_name = "installations/map.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["map_tile_url"] = settings.MAP_TILE_URL
        context["map_tile_attribution"] = settings.MAP_TILE_ATTRIBUTION
        context["map_tile_max_zoom"] = settings.MAP_TILE_MAX_ZOOM
        return context


class InstallationSearchView(AuthenticatedViewMixin, ListView[Installation]):
    """Globale Suche über Installationen (mehrere Filter, Pagination)."""

    template_name = "installations/search.html"
    context_object_name = "installations"
    paginate_by = 25

    def _installers(self) -> Any:
        scope = current_tenant_or_none()
        qs = User.objects.filter(is_active=True, role__in=[Role.INSTALLER, Role.TENANT_ADMIN])
        if scope is not None:
            qs = qs.filter(tenant=scope)
        return qs.order_by("full_name")

    def get_form(self) -> InstallationSearchForm:
        if not hasattr(self, "_form"):
            self._form = InstallationSearchForm(
                self.request.GET or None,
                projects=visible_projects(self.acting_user),
                installers=self._installers(),
            )
        return self._form

    def get_queryset(self) -> Any:
        form = self.get_form()
        if not form.is_valid():
            return services.search_installations(self.acting_user)
        data = form.cleaned_data
        date_from = (
            timezone.make_aware(datetime.combine(data["date_from"], time.min))
            if data.get("date_from")
            else None
        )
        date_to = (
            timezone.make_aware(datetime.combine(data["date_to"], time.max))
            if data.get("date_to")
            else None
        )
        return services.search_installations(
            self.acting_user,
            search=data.get("q", ""),
            project_id=data["project"].pk if data.get("project") else None,
            deveui=data.get("deveui", ""),
            installer_id=data["installer"].pk if data.get("installer") else None,
            date_from=date_from,
            date_to=date_to,
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["form"] = self.get_form()
        return context


class InstallationDetailView(AuthenticatedViewMixin, TemplateView):
    """Detailansicht einer Installation inkl. Fotos und administrativer Aktionen."""

    template_name = "installations/installation_detail.html"

    def get_installation(self) -> Installation:
        if not hasattr(self, "_installation"):
            try:
                self._installation = services.get_visible_installation(
                    self.acting_user, self.kwargs["pk"]
                )
            except Installation.DoesNotExist as exc:
                raise Http404("Installation nicht gefunden.") from exc
        return self._installation

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        installation = self.get_installation()
        context["installation"] = installation
        context["photos"] = installation.photos.all()
        context["can_manage"] = self.acting_user.can_manage_users
        return context


class InstallationCorrectView(AdminRequiredMixin, FormView[InstallationCorrectForm]):
    """Administrative Korrektur einer Installation (Projekt, Beschreibung)."""

    template_name = "installations/installation_correct.html"
    form_class = InstallationCorrectForm

    def get_installation(self) -> Installation:
        if not hasattr(self, "_installation"):
            try:
                self._installation = services.get_visible_installation(
                    self.acting_user, self.kwargs["pk"]
                )
            except Installation.DoesNotExist as exc:
                raise Http404("Installation nicht gefunden.") from exc
        return self._installation

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["projects"] = visible_projects(self.acting_user)
        installation = self.get_installation()
        kwargs.setdefault("initial", {})
        kwargs["initial"].update(
            {"project": installation.project_id, "description": installation.description}
        )
        return kwargs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["installation"] = self.get_installation()
        return context

    def form_valid(self, form: InstallationCorrectForm) -> HttpResponse:
        installation = self.get_installation()
        services.correct_installation(
            installation,
            project=form.cleaned_data["project"],
            description=form.cleaned_data["description"],
            actor=self.acting_user,
            request=self.request,
        )
        messages.success(self.request, "Installation korrigiert.")
        return redirect("installations:detail", pk=installation.pk)


class InstallationCancelView(AdminRequiredMixin, View):
    """Storniert eine Installation (nur per POST, mit Begründung)."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponseRedirect:
        try:
            installation = services.get_visible_installation(self.acting_user, pk)
        except Installation.DoesNotExist as exc:
            raise Http404("Installation nicht gefunden.") from exc
        form = InstallationCancelForm(request.POST)
        if form.is_valid():
            services.cancel_installation(
                installation,
                reason=form.cleaned_data["reason"],
                actor=self.acting_user,
                request=request,
            )
            messages.success(request, "Installation storniert.")
        else:
            messages.error(request, "Bitte einen Stornogrund angeben.")
        return redirect("installations:detail", pk=installation.pk)
