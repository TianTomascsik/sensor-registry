"""Views der Geräteanmeldung.

* Registrierung (anonym): Ein Monteur öffnet den Einladungslink und registriert sein Gerät.
* Verwaltung (Administratoren): Einladungen erstellen/widerrufen, Geräte sperren/entfernen.
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseBase,
    HttpResponseRedirect,
)
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import FormView, TemplateView

from apps.accounts import devices
from apps.accounts.forms import DeviceRegisterForm, InviteCreateForm
from apps.accounts.models import Device, DeviceInvite, Role, User
from apps.core.permissions import AdminRequiredMixin
from apps.core.tenancy import current_tenant, current_tenant_or_none

# Session-Schlüssel für die einmalige Anzeige des frisch erzeugten Einladungslinks.
_FRESH_INVITE_SESSION_KEY = "fresh_invite"


# --- Registrierung (anonym) --------------------------------------------------------


class DeviceRegisterView(View):
    """Registrierung eines Geräts über einen Einladungslink (ohne Anmeldung)."""

    def get(self, request: HttpRequest, token: str) -> HttpResponse:
        invite = devices.get_invite_by_token(token)
        if invite is None or not invite.is_valid:
            return self._render_invalid(request, invite)
        return render(
            request,
            "devices/register.html",
            {"invite": invite, "form": DeviceRegisterForm(), "token": token},
        )

    def post(self, request: HttpRequest, token: str) -> HttpResponse:
        invite = devices.get_invite_by_token(token)
        if invite is None or not invite.is_valid:
            return self._render_invalid(request, invite)

        form = DeviceRegisterForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                "devices/register.html",
                {"invite": invite, "form": form, "token": token},
            )

        try:
            _device, raw_token = devices.redeem_invite(
                invite,
                label=form.cleaned_data["label"],
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
                request=request,
            )
        except devices.InviteRedemptionError:
            return self._render_invalid(request, invite)

        response = redirect("core:dashboard")
        devices.set_device_cookie(response, raw_token)
        messages.success(request, "Gerät registriert. Sie bleiben auf diesem Gerät angemeldet.")
        return response

    @staticmethod
    def _render_invalid(request: HttpRequest, invite: DeviceInvite | None) -> HttpResponse:
        if invite is not None and invite.is_used:
            reason = "Diese Einladung wurde bereits verwendet."
        elif invite is not None and invite.is_expired:
            reason = "Diese Einladung ist abgelaufen."
        else:
            reason = "Dieser Einladungslink ist ungültig."
        return render(request, "devices/register_invalid.html", {"reason": reason}, status=400)


# --- Verwaltung (Administratoren) --------------------------------------------------


class DeviceListView(AdminRequiredMixin, TemplateView):
    """Übersicht der Geräte und offenen Einladungen."""

    template_name = "devices/device_list.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["devices"] = devices.list_devices()
        context["invites"] = devices.list_pending_invites()
        context["has_tenant"] = current_tenant_or_none() is not None
        return context


class InviteCreateView(AdminRequiredMixin, FormView[InviteCreateForm]):
    """Erstellt eine Geräteeinladung für einen Monteur."""

    template_name = "devices/invite_form.html"
    form_class = InviteCreateForm

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        if request.user.is_authenticated and current_tenant_or_none() is None:
            messages.info(request, "Bitte zuerst oben einen Mandanten auswählen.")
            return redirect("devices:list")
        return super().dispatch(request, *args, **kwargs)

    def _installers(self) -> Any:
        return User.objects.filter(
            tenant=current_tenant(), role=Role.INSTALLER, is_active=True
        ).order_by("full_name")

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["installers"] = self._installers()
        return kwargs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["has_installers"] = self._installers().exists()
        return context

    def form_valid(self, form: InviteCreateForm) -> HttpResponse:
        invite, raw_token = devices.create_invite(
            user=form.cleaned_data["user"], actor=self.acting_user, request=self.request
        )
        # Klartext-Token nur einmalig über die Session an die Anzeige-Seite weiterreichen.
        self.request.session[_FRESH_INVITE_SESSION_KEY] = {"id": invite.pk, "token": raw_token}
        return redirect("devices:invite_show")


class InviteShowView(AdminRequiredMixin, TemplateView):
    """Zeigt den frisch erzeugten Einladungslink samt QR-Code – nur einmalig."""

    template_name = "devices/invite_show.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        fresh = self.request.session.pop(_FRESH_INVITE_SESSION_KEY, None)
        if not fresh:
            context["available"] = False
            return context
        try:
            invite = devices.get_managed_invite(fresh["id"])
        except DeviceInvite.DoesNotExist:
            context["available"] = False
            return context
        url = self.request.build_absolute_uri(reverse("devices:register", args=[fresh["token"]]))
        context["available"] = True
        context["invite"] = invite
        context["invite_url"] = url
        context["qr_data_uri"] = devices.qr_png_data_uri(url)
        return context


class InviteRevokeView(AdminRequiredMixin, View):
    """Widerruft eine offene Einladung (nur per POST)."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponseRedirect:
        try:
            invite = devices.get_managed_invite(pk)
        except DeviceInvite.DoesNotExist as exc:
            raise Http404("Einladung nicht gefunden.") from exc
        devices.revoke_invite(invite, actor=self.acting_user, request=request)
        messages.success(request, "Einladung widerrufen.")
        return redirect("devices:list")


class DeviceRevokeView(AdminRequiredMixin, View):
    """Sperrt ein Gerät (nur per POST)."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponseRedirect:
        try:
            device = devices.get_managed_device(pk)
        except Device.DoesNotExist as exc:
            raise Http404("Gerät nicht gefunden.") from exc
        devices.revoke_device(device, actor=self.acting_user, request=request)
        messages.success(request, "Gerät gesperrt.")
        return redirect("devices:list")


class DeviceRemoveView(AdminRequiredMixin, View):
    """Entfernt ein Gerät vollständig (nur per POST)."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponseRedirect:
        try:
            device = devices.get_managed_device(pk)
        except Device.DoesNotExist as exc:
            raise Http404("Gerät nicht gefunden.") from exc
        devices.remove_device(device, actor=self.acting_user, request=request)
        messages.success(request, "Gerät entfernt.")
        return redirect("devices:list")
