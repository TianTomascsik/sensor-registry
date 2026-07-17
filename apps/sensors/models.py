"""Sensormodell.

Ein ``Sensor`` beschreibt die Stammdaten eines LoRaWAN-Bodensensors. Die eigentliche
Einbaudokumentation (Installation) folgt in einer späteren Phase; ein Sensor kann später
mehrfach ein- und ausgebaut werden.
"""

from __future__ import annotations

from typing import Any

from django.core.validators import RegexValidator
from django.db import models

from apps.core.tenancy import TenantModel

#: Ein DevEUI besteht aus genau 16 Hexadezimalzeichen (64 Bit), hier in Großschreibung.
DEVEUI_VALIDATOR = RegexValidator(
    regex=r"^[0-9A-F]{16}$",
    message="Der DevEUI muss aus genau 16 Hexadezimalzeichen (0-9, A-F) bestehen.",
)


def normalize_deveui(raw: str) -> str:
    """Normalisiert eine DevEUI-Eingabe auf 16 Hexzeichen in Großschreibung.

    Übliche Trennzeichen (Leerzeichen, Doppelpunkt, Bindestrich) werden entfernt, damit
    z. B. ``70:B3:D5:7E:D0:01:23:45`` und ``70B3D57ED0012345`` als identisch gelten.
    """
    cleaned = raw.strip().upper()
    for separator in (" ", ":", "-", "."):
        cleaned = cleaned.replace(separator, "")
    return cleaned


class Sensor(TenantModel):
    """Stammdaten eines LoRaWAN-Bodensensors (mandantengebunden)."""

    dev_eui = models.CharField(
        "DevEUI",
        max_length=16,
        validators=[DEVEUI_VALIDATOR],
        help_text="16 Hexadezimalzeichen; Trennzeichen werden automatisch entfernt.",
    )
    manufacturer = models.CharField("Hersteller", max_length=120, blank=True)
    sensor_type = models.CharField("Typ", max_length=120, blank=True)
    serial_number = models.CharField("Seriennummer", max_length=120, blank=True)
    note = models.TextField("Bemerkung", blank=True)

    class Meta:
        verbose_name = "Sensor"
        verbose_name_plural = "Sensoren"
        ordering = ["dev_eui"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "dev_eui"],
                name="sensor_deveui_unique_per_tenant",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "dev_eui"]),
        ]

    def __str__(self) -> str:
        return self.dev_eui

    def save(self, *args: Any, **kwargs: Any) -> None:
        # DevEUI stets normalisiert speichern, damit die Eindeutigkeit zuverlässig greift.
        self.dev_eui = normalize_deveui(self.dev_eui)
        super().save(*args, **kwargs)
