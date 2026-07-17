"""Signale, die Anmelde-Ereignisse ins Audit-Log schreiben.

Django sendet ``user_logged_in``, ``user_logged_out`` und ``user_login_failed``. Diese
zentrale Anbindung stellt sicher, dass jede Anmeldung – erfolgreich oder nicht – protokolliert
wird, unabhängig davon, über welchen Pfad sie ausgelöst wurde.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.dispatch import receiver
from django.http import HttpRequest

from apps.accounts.models import User
from apps.audit.models import AuditAction
from apps.audit.services import record


@receiver(user_logged_in)
def on_logged_in(sender: Any, request: HttpRequest, user: User, **kwargs: Any) -> None:
    record(AuditAction.LOGIN, actor=user, request=request)


@receiver(user_logged_out)
def on_logged_out(sender: Any, request: HttpRequest, user: User | None, **kwargs: Any) -> None:
    record(AuditAction.LOGOUT, actor=user, request=request)


@receiver(user_login_failed)
def on_login_failed(
    sender: Any, credentials: dict[str, Any], request: HttpRequest | None = None, **kwargs: Any
) -> None:
    # Die Anmeldedaten enthalten die versuchte E-Mail (nie das Passwort protokollieren).
    attempted = credentials.get("username") or credentials.get("email") or ""
    record(
        AuditAction.LOGIN_FAILED,
        request=request,
        changes={"email": attempted},
    )
