"""Service-Layer der Installationsdokumentation.

Enthält die gesamte Geschäftslogik: idempotente Erfassung (für den späteren Offline-Sync),
Wiedereinbau-Logik, Fotoverarbeitung, administrative Korrektur/Storno sowie die
rollenbasierten Abfragen für Liste, Karte und Suche.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q, QuerySet
from django.http import HttpRequest
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.installations.imaging import process_image
from apps.installations.models import Installation, InstallationPhoto, InstallationStatus
from apps.projects.models import Project
from apps.sensors.models import Sensor

# --- Abfragen / Sichtbarkeit -------------------------------------------------------


def visible_installations(user: User) -> QuerySet[Installation]:
    """Basis-Queryset der für den Benutzer sichtbaren Installationen (mandantengefiltert).

    Monteure sehen nur Installationen ihrer zugewiesenen Projekte; Administratoren alle des
    Mandanten.
    """
    qs = Installation.objects.select_related("sensor", "project", "installer")
    if user.role == Role.INSTALLER:
        qs = qs.filter(project__assignments__user=user)
    return qs.distinct()


def get_visible_installation(user: User, pk: int) -> Installation:
    """Lädt eine sichtbare Installation (sonst ``Installation.DoesNotExist``)."""
    return visible_installations(user).get(pk=pk)


def search_installations(
    user: User,
    *,
    search: str = "",
    project_id: int | None = None,
    deveui: str = "",
    installer_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> QuerySet[Installation]:
    """Durchsucht die sichtbaren Installationen nach mehreren Kriterien."""
    qs = visible_installations(user)
    term = search.strip()
    if term:
        qs = qs.filter(
            Q(description__icontains=term)
            | Q(sensor__dev_eui__icontains=term)
            | Q(project__number__icontains=term)
            | Q(project__name__icontains=term)
        )
    if project_id:
        qs = qs.filter(project_id=project_id)
    if deveui.strip():
        qs = qs.filter(sensor__dev_eui__icontains=deveui.strip().upper())
    if installer_id:
        qs = qs.filter(installer_id=installer_id)
    if date_from:
        qs = qs.filter(received_at__gte=date_from)
    if date_to:
        qs = qs.filter(received_at__lte=date_to)
    return qs


def map_installations(user: User) -> QuerySet[Installation]:
    """Aktive (eingebaute, nicht stornierte) Installationen für die Kartenansicht."""
    return visible_installations(user).filter(
        status=InstallationStatus.INSTALLED, cancelled_at__isnull=True
    )


# --- Erfassung ---------------------------------------------------------------------


def create_installation(
    *,
    client_uuid: uuid.UUID,
    sensor: Sensor,
    project: Project,
    installer: User,
    latitude: Decimal,
    longitude: Decimal,
    accuracy_m: float,
    captured_at: datetime,
    gps_timestamp: datetime | None = None,
    description: str = "",
    actor: User,
    request: HttpRequest | None = None,
) -> tuple[Installation, bool]:
    """Erfasst eine Installation – idempotent über ``client_uuid``.

    Existiert bereits eine Installation mit dieser ``client_uuid``, wird sie unverändert
    zurückgegeben (idempotenter Sync-Replay). Andernfalls wird ein etwaiger aktiver Einbau
    desselben Sensors transaktional auf „ausgebaut“ gesetzt (Wiedereinbau) und die neue
    Installation angelegt.

    :returns: Tupel ``(installation, created)``.
    """
    with transaction.atomic():
        existing = Installation.objects.select_for_update().filter(client_uuid=client_uuid).first()
        if existing is not None:
            return existing, False

        # Wiedereinbau: bisher aktive Installation dieses Sensors ausbauen.
        Installation.objects.filter(
            sensor=sensor,
            status=InstallationStatus.INSTALLED,
            cancelled_at__isnull=True,
        ).update(status=InstallationStatus.REMOVED)

        installation = Installation.objects.create(
            client_uuid=client_uuid,
            sensor=sensor,
            project=project,
            installer=installer,
            latitude=latitude,
            longitude=longitude,
            accuracy_m=accuracy_m,
            captured_at=captured_at,
            gps_timestamp=gps_timestamp,
            description=description,
            status=InstallationStatus.INSTALLED,
        )
    record(
        AuditAction.INSTALLATION_CREATED,
        actor=actor,
        obj=installation,
        changes={"sensor": sensor.dev_eui, "projekt": project.number},
        request=request,
    )
    return installation, True


def add_photo(
    *,
    installation: Installation,
    image_bytes: bytes,
    client_uuid: uuid.UUID,
    order: int = 0,
    actor: User,
    request: HttpRequest | None = None,
) -> tuple[InstallationPhoto, bool]:
    """Fügt einer Installation ein Foto hinzu – idempotent über ``client_uuid``.

    Das Bild wird validiert und neu kodiert (Original + Thumbnail). Existiert bereits ein Foto
    mit dieser ``client_uuid``, wird es unverändert zurückgegeben.
    """
    existing = installation.photos.filter(client_uuid=client_uuid).first()
    if existing is not None:
        return existing, False

    original_bytes, thumb_bytes = process_image(image_bytes)
    photo_uuid = uuid.uuid4()
    photo = InstallationPhoto(
        installation=installation,
        client_uuid=client_uuid,
        photo_uuid=photo_uuid,
        order=order,
    )
    photo.original.save(f"{photo_uuid}.jpg", ContentFile(original_bytes), save=False)
    photo.thumbnail.save(f"{photo_uuid}_thumb.jpg", ContentFile(thumb_bytes), save=False)
    photo.save()

    record(
        AuditAction.INSTALLATION_PHOTO_ADDED,
        actor=actor,
        obj=installation,
        changes={"foto": str(photo_uuid)},
        request=request,
    )
    return photo, True


# --- Administrative Korrektur / Storno ---------------------------------------------


def correct_installation(
    installation: Installation,
    *,
    project: Project,
    description: str,
    actor: User,
    request: HttpRequest | None = None,
) -> Installation:
    """Korrigiert Projektzuordnung und Beschreibung einer Installation (Administratoren)."""
    changes: dict[str, dict[str, str]] = {}
    if installation.project_id != project.pk:
        changes["projekt"] = {"von": installation.project.number, "zu": project.number}
        installation.project = project
    if installation.description != description:
        changes["beschreibung"] = {"von": installation.description, "zu": description}
        installation.description = description
    if changes:
        installation.save(update_fields=["project", "description"])
        record(
            AuditAction.INSTALLATION_CORRECTED,
            actor=actor,
            obj=installation,
            changes=changes,
            request=request,
        )
    return installation


def cancel_installation(
    installation: Installation,
    *,
    reason: str,
    actor: User,
    request: HttpRequest | None = None,
) -> Installation:
    """Storniert eine Installation (statt sie zu löschen – die Historie bleibt erhalten)."""
    if installation.cancelled_at is None:
        installation.cancelled_at = timezone.now()
        installation.cancellation_reason = reason
        installation.save(update_fields=["cancelled_at", "cancellation_reason"])
        record(
            AuditAction.INSTALLATION_CANCELLED,
            actor=actor,
            obj=installation,
            changes={"grund": reason},
            request=request,
        )
    return installation
