"""Authentifizierungs-Backend.

Erweitert Djangos ``ModelBackend`` um eine zusätzliche Sperre: Benutzer eines
deaktivierten Mandanten können sich nirgends anmelden (Defense in Depth – unabhängig von
der Prüfung in der View).
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.backends import ModelBackend
from django.http import HttpRequest

from apps.accounts.models import User


class EmailBackend(ModelBackend):
    """Anmeldung per E-Mail-Adresse und Passwort."""

    def user_can_authenticate(self, user: Any) -> bool:
        if not super().user_can_authenticate(user):
            return False
        if isinstance(user, User) and not user.is_superadmin:
            # Nicht-Superadmins benötigen einen aktiven Mandanten.
            return user.tenant is not None and user.tenant.is_active
        return True

    def authenticate(
        self,
        request: HttpRequest | None,
        username: str | None = None,
        password: str | None = None,
        **kwargs: Any,
    ) -> User | None:
        user = super().authenticate(request, username=username, password=password, **kwargs)
        return user if isinstance(user, User) else None
