"""Kernmodelle: der Mandant (Tenant) als Wurzel der Datentrennung.

``Tenant`` selbst ist bewusst **nicht** mandantengebunden (er ist die Wurzel) und daher
von der Mandantenprüfung ausgenommen (:attr:`tenant_exempt`).
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Tenant(models.Model):
    """Ein Mandant (Firma). Wurzel-Entität der Mandantentrennung.

    Alle mandantengebundenen Daten verweisen per Fremdschlüssel auf genau einen Tenant.
    Deaktivierte Mandanten (``is_active=False``) sperren die Anmeldung all ihrer Benutzer.
    """

    #: Von der Mandantenprüfung ausgenommen – Tenant ist selbst die Trennungswurzel.
    tenant_exempt = True

    name = models.CharField("Name", max_length=200)
    slug = models.SlugField("Kürzel", max_length=60, unique=True)
    is_active = models.BooleanField("Aktiv", default=True)
    gps_accuracy_threshold_m = models.PositiveIntegerField(
        "GPS-Genauigkeitsgrenze (Meter)",
        default=settings.GPS_ACCURACY_DEFAULT_THRESHOLD_M,
        validators=[MinValueValidator(1)],
        help_text="Ist die gemessene Genauigkeit schlechter als dieser Wert, "
        "wird der Monteur bei der Installation gewarnt.",
    )
    created_at = models.DateTimeField("Erstellt am", default=timezone.now, editable=False)

    class Meta:
        verbose_name = "Mandant"
        verbose_name_plural = "Mandanten"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
