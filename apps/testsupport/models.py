"""Hilfsmodelle für Tests (nur unter ``config.settings.test`` geladen).

``ScopedThing`` ist ein minimales mandantengebundenes Modell, an dem die Durchsetzung der
Mandantentrennung (:class:`apps.core.tenancy.TenantModel`) geprüft wird, bevor in Phase 2
echte Fachmodelle hinzukommen.
"""

from __future__ import annotations

from django.db import models

from apps.core.tenancy import TenantModel


class ScopedThing(TenantModel):
    """Minimales mandantengebundenes Testmodell."""

    name = models.CharField("Name", max_length=50)

    class Meta:
        verbose_name = "Testobjekt"
        verbose_name_plural = "Testobjekte"

    def __str__(self) -> str:
        return self.name
