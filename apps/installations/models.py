"""Modelle der Installationsdokumentation.

Eine ``Installation`` hält fest, dass ein Sensor zu einem Zeitpunkt durch einen Monteur an
einer GPS-Position in einem Projekt eingebaut wurde. Ein Sensor kann später ausgebaut und
erneut eingebaut werden; alle Installationen bleiben historisch erhalten.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.tenancy import TenantModel


class InstallationStatus(models.TextChoices):
    """Zustand einer Installation (kompaktes Modell)."""

    INSTALLED = "installed", "Eingebaut"
    REMOVED = "removed", "Ausgebaut"


def _photo_upload_path(instance: InstallationPhoto, filename: str) -> str:
    """Baut den mandantengetrennten Ablagepfad eines Fotos.

    ``media/tenants/<tenant>/projects/<projekt>/installations/<installation-uuid>/<datei>``
    """
    inst = instance.installation
    return (
        f"tenants/{inst.tenant_id}/projects/{inst.project_id}/"
        f"installations/{inst.client_uuid}/{filename}"
    )


class Installation(TenantModel):
    """Eine dokumentierte Sensor-Installation (unveränderliche Historie)."""

    #: Vom Client erzeugte UUID zur idempotenten Synchronisation (Offline-Betrieb, Phase 6).
    client_uuid = models.UUIDField("Client-UUID", default=uuid.uuid4, editable=False)

    sensor = models.ForeignKey(
        "sensors.Sensor",
        on_delete=models.PROTECT,
        related_name="installations",
        verbose_name="Sensor",
    )
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.PROTECT,
        related_name="installations",
        verbose_name="Projekt",
    )
    installer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="installations",
        verbose_name="Monteur",
    )

    # GPS (Pflicht – ohne Position ist keine Installation möglich).
    latitude = models.DecimalField("Breitengrad", max_digits=9, decimal_places=6)
    longitude = models.DecimalField("Längengrad", max_digits=9, decimal_places=6)
    accuracy_m = models.FloatField("Genauigkeit (Meter)", validators=[MinValueValidator(0.0)])
    gps_timestamp = models.DateTimeField("GPS-Zeitstempel", null=True, blank=True)

    # Zeitpunkte: Client-Uhr (captured_at) getrennt von der auditfesten Server-Uhr.
    captured_at = models.DateTimeField("Erfasst am (Gerät)")
    received_at = models.DateTimeField(
        "Empfangen am (Server)", default=timezone.now, editable=False
    )

    description = models.TextField("Beschreibung", blank=True)
    status = models.CharField(
        "Status",
        max_length=20,
        choices=InstallationStatus.choices,
        default=InstallationStatus.INSTALLED,
    )

    # Administrativer Storno (statt Löschen – die Historie bleibt erhalten).
    cancelled_at = models.DateTimeField("Storniert am", null=True, blank=True)
    cancellation_reason = models.TextField("Stornogrund", blank=True)

    class Meta:
        verbose_name = "Installation"
        verbose_name_plural = "Installationen"
        ordering = ["-received_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "client_uuid"],
                name="installation_client_uuid_unique_per_tenant",
            ),
            # Höchstens eine aktive (eingebaute, nicht stornierte) Installation je Sensor.
            models.UniqueConstraint(
                fields=["sensor"],
                condition=models.Q(status="installed", cancelled_at__isnull=True),
                name="one_active_installation_per_sensor",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "-received_at"]),
            models.Index(fields=["sensor"]),
            models.Index(fields=["project"]),
            # Beschleunigt die Volltext-/Teilstring-Suche in der Beschreibung.
            GinIndex(
                name="installation_desc_trgm",
                fields=["description"],
                opclasses=["gin_trgm_ops"],
            ),
        ]

    def __str__(self) -> str:
        return f"{self.sensor_id} @ {self.received_at:%Y-%m-%d}"

    @property
    def is_cancelled(self) -> bool:
        return self.cancelled_at is not None

    @property
    def is_active(self) -> bool:
        return self.status == InstallationStatus.INSTALLED and not self.is_cancelled


class InstallationPhoto(TenantModel):
    """Ein Foto einer Installation (Original + Thumbnail, lokal gespeichert)."""

    installation = models.ForeignKey(
        Installation,
        on_delete=models.CASCADE,
        related_name="photos",
        verbose_name="Installation",
    )
    #: Vom Client erzeugte UUID zur idempotenten Foto-Synchronisation.
    client_uuid = models.UUIDField("Client-UUID", default=uuid.uuid4, editable=False)
    #: Serverseitige UUID für Dateinamen und die öffentliche (geschützte) URL.
    photo_uuid = models.UUIDField("Foto-UUID", default=uuid.uuid4, editable=False, unique=True)

    original = models.FileField("Original", upload_to=_photo_upload_path, max_length=300)
    thumbnail = models.FileField("Thumbnail", upload_to=_photo_upload_path, max_length=300)
    order = models.PositiveIntegerField("Reihenfolge", default=0)
    created_at = models.DateTimeField("Hochgeladen am", default=timezone.now, editable=False)

    class Meta:
        verbose_name = "Installationsfoto"
        verbose_name_plural = "Installationsfotos"
        ordering = ["order", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["installation", "client_uuid"],
                name="photo_client_uuid_unique_per_installation",
            ),
        ]

    def __str__(self) -> str:
        return f"Foto {self.photo_uuid}"
