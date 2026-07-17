"""Views der Accounts-App: Anmeldung, Abmeldung und Benutzerverwaltung.

Die Views bleiben bewusst schlank – die Geschäftslogik liegt im Service-Layer
(:mod:`apps.accounts.services`).
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseBase,
    HttpResponseRedirect,
)
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import FormView, ListView
from django_ratelimit.decorators import ratelimit

from apps.accounts import services
from apps.accounts.forms import LoginForm, UserCreateForm, UserUpdateForm
from apps.accounts.models import User
from apps.core.permissions import ManageUsersRequiredMixin
from apps.core.tenancy import current_tenant_or_none

# Begrenzt Anmeldeversuche pro IP-Adresse und pro angefragter E-Mail (Brute-Force-Schutz).
_ratelimit_ip = ratelimit(key="ip", rate="10/m", method="POST", block=False)
_ratelimit_email = ratelimit(key="post:email", rate="5/m", method="POST", block=False)


@_ratelimit_ip
@_ratelimit_email
def login_view(request: HttpRequest) -> HttpResponse:
    """Meldet einen Benutzer per E-Mail und Passwort an."""
    if request.user.is_authenticated:
        return redirect("core:dashboard")

    form = LoginForm(request.POST or None)
    if request.method == "POST":
        if getattr(request, "limited", False):
            messages.error(request, "Zu viele Anmeldeversuche. Bitte kurz warten.")
        elif form.is_valid():
            user = authenticate(
                request,
                username=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
            )
            if user is not None:
                login(request, user)
                return redirect(_safe_next(request))
            messages.error(request, "E-Mail-Adresse oder Passwort ist falsch.")
    return render(request, "accounts/login.html", {"form": form})


def _safe_next(request: HttpRequest) -> str:
    """Gibt ein sicheres Weiterleitungsziel zurück (verhindert Open-Redirects)."""
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(
        nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return nxt
    return reverse("core:dashboard")


def logout_view(request: HttpRequest) -> HttpResponse:
    """Meldet den aktuellen Benutzer ab (nur per POST, CSRF-geschützt)."""
    if request.method == "POST":
        logout(request)
    return redirect("accounts:login")


class UserListView(ManageUsersRequiredMixin, ListView[User]):
    """Listet die im aktuellen Kontext verwaltbaren Benutzer."""

    template_name = "accounts/user_list.html"
    context_object_name = "users"
    paginate_by = 25

    def get_queryset(self) -> Any:
        return services.list_users()


class UserCreateView(ManageUsersRequiredMixin, FormView[UserCreateForm]):
    """Legt einen Benutzer innerhalb des aktiven Mandanten an."""

    template_name = "accounts/user_form.html"
    form_class = UserCreateForm
    success_url = reverse_lazy("accounts:user_list")

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        response = self._require_active_tenant(request)
        if response is not None:
            return response
        return super().dispatch(request, *args, **kwargs)

    def _require_active_tenant(self, request: HttpRequest) -> HttpResponse | None:
        """Superadmins müssen vor dem Anlegen einen Mandanten gewählt haben."""
        if request.user.is_authenticated and current_tenant_or_none() is None:
            messages.info(request, "Bitte zuerst oben einen Mandanten auswählen.")
            return redirect("accounts:user_list")
        return None

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["role_choices"] = services.assignable_roles(self.acting_user)
        return kwargs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Benutzer anlegen"
        return context

    def form_valid(self, form: UserCreateForm) -> HttpResponse:
        tenant = current_tenant_or_none()
        assert tenant is not None  # durch _require_active_tenant sichergestellt
        services.create_user(
            tenant=tenant,
            email=form.cleaned_data["email"],
            full_name=form.cleaned_data["full_name"],
            role=form.cleaned_data["role"],
            password=form.cleaned_data["password"] or None,
            actor=self.acting_user,
            request=self.request,
        )
        messages.success(self.request, "Benutzer angelegt.")
        return super().form_valid(form)


class UserUpdateView(ManageUsersRequiredMixin, FormView[UserUpdateForm]):
    """Ändert Name und Rolle eines Benutzers."""

    template_name = "accounts/user_form.html"
    form_class = UserUpdateForm
    success_url = reverse_lazy("accounts:user_list")

    def get_object(self) -> User:
        # Innerhalb eines Requests zwischenspeichern, um wiederholte Abfragen zu vermeiden.
        if not hasattr(self, "_object"):
            try:
                self._object = services.get_managed_user(self.kwargs["pk"])
            except User.DoesNotExist as exc:
                # Nicht im aktuellen Mandantenkontext sichtbar → wie „nicht vorhanden“.
                raise Http404("Benutzer nicht gefunden.") from exc
        return self._object

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["role_choices"] = services.assignable_roles(self.acting_user)
        user = self.get_object()
        kwargs.setdefault("initial", {})
        kwargs["initial"].update({"full_name": user.full_name, "role": user.role})
        return kwargs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Benutzer bearbeiten"
        context["managed_user"] = self.get_object()
        return context

    def form_valid(self, form: UserUpdateForm) -> HttpResponse:
        services.update_user(
            self.get_object(),
            full_name=form.cleaned_data["full_name"],
            role=form.cleaned_data["role"],
            actor=self.acting_user,
            request=self.request,
        )
        messages.success(self.request, "Benutzer aktualisiert.")
        return super().form_valid(form)


class UserToggleActiveView(ManageUsersRequiredMixin, View):
    """Aktiviert bzw. deaktiviert einen Benutzer (nur per POST)."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponseRedirect:
        try:
            user = services.get_managed_user(pk)
        except User.DoesNotExist as exc:
            raise Http404("Benutzer nicht gefunden.") from exc
        if user == request.user:
            messages.error(request, "Sie können sich nicht selbst deaktivieren.")
            return redirect("accounts:user_list")
        services.set_user_active(
            user, active=not user.is_active, actor=self.acting_user, request=request
        )
        messages.success(
            request, "Benutzer aktiviert." if user.is_active else "Benutzer deaktiviert."
        )
        return redirect("accounts:user_list")
