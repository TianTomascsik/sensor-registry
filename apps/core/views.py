"""Views der Kern-App: Dashboard, Mandantenverwaltung und Mandanten-Umschalter."""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import FormView, ListView, TemplateView

from apps.core import services
from apps.core.forms import TenantCreateForm, TenantUpdateForm
from apps.core.middleware import ACTIVE_TENANT_SESSION_KEY
from apps.core.models import Tenant
from apps.core.permissions import SuperadminRequiredMixin


class DashboardView(LoginRequiredMixin, TemplateView):
    """Startseite nach der Anmeldung."""

    template_name = "core/dashboard.html"


class TenantListView(SuperadminRequiredMixin, ListView[Tenant]):
    """Mandantenübersicht (nur Superadmin)."""

    template_name = "core/tenant_list.html"
    context_object_name = "tenants"
    paginate_by = 25

    def get_queryset(self) -> Any:
        return services.list_tenants()


class TenantCreateView(SuperadminRequiredMixin, FormView[TenantCreateForm]):
    """Legt einen neuen Mandanten an."""

    template_name = "core/tenant_form.html"
    form_class = TenantCreateForm
    success_url = reverse_lazy("core:tenant_list")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Mandant anlegen"
        return context

    def form_valid(self, form: TenantCreateForm) -> HttpResponse:
        services.create_tenant(
            name=form.cleaned_data["name"],
            slug=form.cleaned_data["slug"],
            gps_accuracy_threshold_m=form.cleaned_data["gps_accuracy_threshold_m"],
            actor=self.acting_user,
            request=self.request,
        )
        messages.success(self.request, "Mandant angelegt.")
        return super().form_valid(form)


class TenantUpdateView(SuperadminRequiredMixin, FormView[TenantUpdateForm]):
    """Ändert die Stammdaten eines Mandanten."""

    template_name = "core/tenant_form.html"
    form_class = TenantUpdateForm
    success_url = reverse_lazy("core:tenant_list")

    def get_object(self) -> Tenant:
        if not hasattr(self, "_object"):
            self._object = Tenant.objects.get(pk=self.kwargs["pk"])
        return self._object

    def get_initial(self) -> dict[str, Any]:
        tenant = self.get_object()
        return {
            "name": tenant.name,
            "gps_accuracy_threshold_m": tenant.gps_accuracy_threshold_m,
        }

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Mandant bearbeiten"
        context["tenant_obj"] = self.get_object()
        return context

    def form_valid(self, form: TenantUpdateForm) -> HttpResponse:
        services.update_tenant(
            self.get_object(),
            name=form.cleaned_data["name"],
            gps_accuracy_threshold_m=form.cleaned_data["gps_accuracy_threshold_m"],
            actor=self.acting_user,
            request=self.request,
        )
        messages.success(self.request, "Mandant aktualisiert.")
        return super().form_valid(form)


class TenantToggleActiveView(SuperadminRequiredMixin, View):
    """Aktiviert bzw. deaktiviert einen Mandanten (nur per POST)."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponseRedirect:
        tenant = Tenant.objects.get(pk=pk)
        services.set_tenant_active(
            tenant, active=not tenant.is_active, actor=self.acting_user, request=request
        )
        # Deaktivierten Mandanten ggf. aus der aktiven Auswahl entfernen.
        if not tenant.is_active and request.session.get(ACTIVE_TENANT_SESSION_KEY) == tenant.pk:
            request.session.pop(ACTIVE_TENANT_SESSION_KEY, None)
        messages.success(
            request, "Mandant aktiviert." if tenant.is_active else "Mandant deaktiviert."
        )
        return redirect("core:tenant_list")


class TenantSwitchView(SuperadminRequiredMixin, View):
    """Setzt oder löscht den vom Superadmin gewählten aktiven Mandanten (nur per POST)."""

    def post(self, request: HttpRequest) -> HttpResponseRedirect:
        raw = request.POST.get("tenant", "")
        if raw:
            tenant = Tenant.objects.filter(pk=raw, is_active=True).first()
            if tenant is None:
                messages.error(request, "Unbekannter oder inaktiver Mandant.")
            else:
                request.session[ACTIVE_TENANT_SESSION_KEY] = tenant.pk
                messages.success(request, f"Aktiver Mandant: {tenant.name}.")
        else:
            request.session.pop(ACTIVE_TENANT_SESSION_KEY, None)
            messages.success(request, "Mandantenauswahl aufgehoben (Gesamtsicht).")
        return redirect(request.POST.get("next") or "core:dashboard")
