"""REST-API der Installationsdokumentation (``/api/v1/``).

Die Endpunkte sind idempotent über die client-generierten UUIDs ausgelegt – Grundlage für den
späteren Offline-Sync (Phase 6). Bereits vorhandene Datensätze werden bei erneutem Senden
unverändert zurückgegeben (Status 200 statt 201).
"""

from __future__ import annotations

import uuid
from typing import Any, cast

from rest_framework import serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.installations.imaging import InvalidImageError
from apps.installations.models import Installation, InstallationPhoto
from apps.installations.services import (
    add_photo,
    create_installation,
    map_installations,
    search_installations,
    visible_installations,
)
from apps.projects.models import Project
from apps.projects.services import get_visible_project, visible_projects
from apps.sensors.models import Sensor
from apps.sensors.services import list_sensors


def _media_url(request: Request, photo: InstallationPhoto, variant: str) -> str:
    from django.urls import reverse

    return request.build_absolute_uri(
        reverse("installations:media", args=[photo.photo_uuid, variant])
    )


def _user(request: Request) -> User:
    """Der authentifizierte Benutzer (durch IsAuthenticated garantiert)."""
    return cast(User, request.user)


class PhotoSerializer(serializers.Serializer):
    """Serialisiert ein Installationsfoto (nur geschützte URLs, keine Pfade)."""

    photo_uuid = serializers.UUIDField()
    order = serializers.IntegerField()
    original_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    def get_original_url(self, obj: InstallationPhoto) -> str:
        return _media_url(self.context["request"], obj, "original")

    def get_thumbnail_url(self, obj: InstallationPhoto) -> str:
        return _media_url(self.context["request"], obj, "thumb")


class InstallationSerializer(serializers.Serializer):
    """Lese-Darstellung einer Installation für Liste, Detail, Karte und Suche."""

    id = serializers.IntegerField()
    client_uuid = serializers.UUIDField()
    dev_eui = serializers.CharField(source="sensor.dev_eui")
    project_number = serializers.CharField(source="project.number")
    project_name = serializers.CharField(source="project.name")
    installer_name = serializers.CharField(source="installer.full_name")
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    accuracy_m = serializers.FloatField()
    captured_at = serializers.DateTimeField()
    received_at = serializers.DateTimeField()
    status = serializers.CharField()
    status_display = serializers.CharField(source="get_status_display")
    description = serializers.CharField()
    thumbnail_url = serializers.SerializerMethodField()
    photos = serializers.SerializerMethodField()

    def _first_photo(self, obj: Installation) -> InstallationPhoto | None:
        return obj.photos.first()

    def get_thumbnail_url(self, obj: Installation) -> str | None:
        photo = self._first_photo(obj)
        if photo is None:
            return None
        return _media_url(self.context["request"], photo, "thumb")

    def get_photos(self, obj: Installation) -> Any:
        return PhotoSerializer(obj.photos.all(), many=True, context=self.context).data


class InstallationCreateSerializer(serializers.Serializer):
    """Validiert die Eingabe zur Erfassung einer Installation."""

    # In den validate_*-Methoden gesetzte, geprüfte Objekte.
    _sensor: Sensor
    _project: Project

    client_uuid = serializers.UUIDField(required=False, default=uuid.uuid4)
    sensor_id = serializers.IntegerField()
    project_id = serializers.IntegerField()
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    accuracy_m = serializers.FloatField(min_value=0)
    captured_at = serializers.DateTimeField()
    gps_timestamp = serializers.DateTimeField(required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_sensor_id(self, value: int) -> int:
        try:
            self._sensor = Sensor.objects.get(pk=value)
        except Sensor.DoesNotExist as exc:
            raise serializers.ValidationError("Unbekannter Sensor.") from exc
        return value

    def validate_project_id(self, value: int) -> int:
        user = self.context["request"].user
        try:
            self._project = get_visible_project(user, value)
        except Project.DoesNotExist as exc:
            raise serializers.ValidationError(
                "Unbekanntes oder nicht zugängliches Projekt."
            ) from exc
        return value


class InstallationCreateAPIView(APIView):
    """Erfasst eine Installation (idempotent über ``client_uuid``)."""

    def post(self, request: Request) -> Response:
        serializer = InstallationCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = _user(request)
        installation, created = create_installation(
            client_uuid=data["client_uuid"],
            sensor=serializer._sensor,
            project=serializer._project,
            installer=user,
            latitude=data["latitude"],
            longitude=data["longitude"],
            accuracy_m=data["accuracy_m"],
            captured_at=data["captured_at"],
            gps_timestamp=data.get("gps_timestamp"),
            description=data.get("description", ""),
            actor=user,
            request=request,
        )
        payload = InstallationSerializer(installation, context={"request": request}).data
        return Response(payload, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class InstallationPhotoAPIView(APIView):
    """Fügt einer Installation ein Foto hinzu (idempotent über die Foto-``client_uuid``)."""

    parser_classes = [MultiPartParser, FormParser]

    def post(self, request: Request, installation_uuid: uuid.UUID) -> Response:
        user = _user(request)
        try:
            installation = visible_installations(user).get(client_uuid=installation_uuid)
        except Installation.DoesNotExist:
            return Response(
                {"detail": "Installation nicht gefunden."}, status=status.HTTP_404_NOT_FOUND
            )

        image = request.FILES.get("image")
        if image is None:
            return Response(
                {"detail": "Es wurde kein Bild übermittelt."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        photo_client_uuid = request.data.get("client_uuid") or uuid.uuid4()
        try:
            order = int(request.data.get("order", 0))
        except (TypeError, ValueError):
            order = 0

        try:
            photo, created = add_photo(
                installation=installation,
                image_bytes=image.read(),
                client_uuid=photo_client_uuid,
                order=order,
                actor=user,
                request=request,
            )
        except InvalidImageError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        payload = PhotoSerializer(photo, context={"request": request}).data
        return Response(payload, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class InstallationListAPIView(APIView):
    """Listet die für den Benutzer sichtbaren Installationen (mit Suchfiltern)."""

    def get(self, request: Request) -> Response:
        qs = search_installations(
            _user(request),
            search=request.query_params.get("q", ""),
            deveui=request.query_params.get("deveui", ""),
        )
        payload = InstallationSerializer(qs[:500], many=True, context={"request": request}).data
        return Response(payload)


class MapInstallationsAPIView(APIView):
    """Liefert die aktiven Installationen als Punktdaten für die Karte."""

    def get(self, request: Request) -> Response:
        qs = map_installations(_user(request))
        payload = InstallationSerializer(qs, many=True, context={"request": request}).data
        return Response(payload)


class RefDataAPIView(APIView):
    """Referenzdaten (aktive Projekte + Sensoren) für das Offline-Replikat.

    Monteure erhalten ihre zugewiesenen, aktiven Projekte; Administratoren alle aktiven
    Projekte des Mandanten. Die Sensoren umfassen alle Sensoren des Mandanten.
    """

    def get(self, request: Request) -> Response:
        user = _user(request)
        projects = list(
            visible_projects(user).filter(status="active").values("id", "number", "name")
        )
        sensors = list(list_sensors().values("id", "dev_eui", "sensor_type"))
        return Response({"projects": projects, "sensors": sensors})
