"""System-Check: erzwingt bewusste Mandanten-Zuordnung für jedes Fachmodell.

Django führt registrierte Checks bei ``migrate``, ``runserver`` und ``check`` aus. Dieser
Check verhindert die häufigste Sicherheitslücke solcher Architekturen: ein neues Modell
wird angelegt, aber die Mandantenbindung schlicht vergessen. Jedes konkrete Modell in den
projekteigenen Apps muss daher entweder

* von :class:`apps.core.tenancy.TenantModel` erben (mandantengebunden), oder
* ``tenant_exempt = True`` setzen (bewusst mandantenübergreifend, z. B. Tenant, User).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from django.apps import apps
from django.core.checks import Error, register

from apps.core.tenancy import TenantModel

#: Präfix, an dem projekteigene Apps erkannt werden.
_LOCAL_APP_PREFIX = "apps."


@register()
def check_tenant_scoping(app_configs: Sequence[Any] | None, **kwargs: Any) -> list[Error]:
    """Stellt sicher, dass jedes projekteigene Modell seine Mandantenbindung deklariert."""
    errors: list[Error] = []
    for model in apps.get_models():
        if not model._meta.app_config.name.startswith(_LOCAL_APP_PREFIX):
            continue
        if issubclass(model, TenantModel):
            continue
        if getattr(model, "tenant_exempt", False):
            continue
        errors.append(
            Error(
                f"Das Modell {model._meta.label} ist weder mandantengebunden noch "
                "ausdrücklich ausgenommen.",
                hint="Von apps.core.tenancy.TenantModel erben (mandantengebunden) oder "
                "'tenant_exempt = True' setzen (bewusst mandantenübergreifend).",
                obj=model,
                id="core.E001",
            )
        )
    return errors
