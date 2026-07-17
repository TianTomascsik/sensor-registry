"""Rollenbasierte Zugriffskontrolle für View-Klassen.

Kapselt die wiederkehrenden Rollenprüfungen an einer Stelle. Nicht angemeldete Benutzer
werden zur Anmeldung geleitet; angemeldete Benutzer ohne passende Rolle erhalten 403.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponseBase

from apps.accounts.models import Role, User


class AuthenticatedViewMixin(LoginRequiredMixin):
    """Basis für Views, die eine Anmeldung erfordern.

    Stellt die typsichere Eigenschaft :attr:`acting_user` bereit – nach ``dispatch`` ist
    der Benutzer garantiert authentifiziert, sodass die Einschränkung auf das konkrete
    Benutzermodell (statt ``AnonymousUser``) korrekt ist.
    """

    request: HttpRequest

    @property
    def acting_user(self) -> User:
        return cast(User, self.request.user)


class RoleRequiredMixin(AuthenticatedViewMixin):
    """Erlaubt den Zugriff nur Benutzern mit einer der ``allowed_roles``."""

    allowed_roles: Iterable[str] = ()

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if request.user.role not in set(self.allowed_roles):
            raise PermissionDenied("Für diese Aktion fehlt die erforderliche Rolle.")
        return super().dispatch(request, *args, **kwargs)


class SuperadminRequiredMixin(RoleRequiredMixin):
    """Nur für Superadmins."""

    allowed_roles = (Role.SUPERADMIN,)


class ManageUsersRequiredMixin(RoleRequiredMixin):
    """Für Benutzerverwaltung: Superadmins und Mandantenadministratoren."""

    allowed_roles = (Role.SUPERADMIN, Role.TENANT_ADMIN)


class AdminRequiredMixin(RoleRequiredMixin):
    """Für die Verwaltung von Projekten und Sensoren: Superadmins und Mandantenadministratoren.

    Bewusst getrennt von :class:`ManageUsersRequiredMixin`, auch wenn beide dieselben
    Rollen zulassen – so bleiben die Zugriffsregeln je Fachbereich unabhängig anpassbar.
    """

    allowed_roles = (Role.SUPERADMIN, Role.TENANT_ADMIN)
