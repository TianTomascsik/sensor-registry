"""Tests der REST-API und der geschützten Medienauslieferung."""

from __future__ import annotations

import io
import json
import uuid

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from PIL import Image

from apps.accounts.devices import generate_token, hash_token
from apps.accounts.models import Device, User
from apps.audit.models import AuditAction, AuditLog
from apps.core.models import Tenant
from apps.core.tenancy import tenant_context
from apps.installations.models import Installation, InstallationPhoto
from apps.projects.models import Project, ProjectAssignment
from apps.sensors.models import Sensor

pytestmark = pytest.mark.django_db

COOKIE = settings.DEVICE_TOKEN_COOKIE_NAME


def _image_bytes(size: tuple[int, int] = (1000, 800)) -> bytes:
    image = Image.new("RGB", size, (90, 140, 190))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
def sensor_a(tenant_a: Tenant) -> Sensor:
    with tenant_context(tenant_a):
        return Sensor.objects.create(dev_eui="AAAAAAAAAAAAAAAA")


@pytest.fixture
def project_a(tenant_a: Tenant) -> Project:
    with tenant_context(tenant_a):
        return Project.objects.create(number="P-1", name="Projekt", status="active")


@pytest.fixture
def installer_device(
    tenant_a: Tenant, project_a: Project, installer_a: User
) -> tuple[Client, User]:
    with tenant_context(tenant_a):
        ProjectAssignment.objects.create(project=project_a, user=installer_a)
    raw = generate_token()
    Device.objects.create(
        tenant=installer_a.tenant, user=installer_a, token_hash=hash_token(raw), label="Testgerät"
    )
    client = Client()
    client.cookies[COOKIE] = raw
    return client, installer_a


def _create_payload(sensor: Sensor, project: Project, client_uuid: uuid.UUID | None = None) -> dict:
    return {
        "client_uuid": str(client_uuid or uuid.uuid4()),
        "sensor_id": sensor.pk,
        "project_id": project.pk,
        "latitude": "47.100000",
        "longitude": "8.200000",
        "accuracy_m": 3.5,
        "captured_at": "2026-07-18T10:00:00Z",
    }


def _post_json(client: Client, url: str, payload: dict):
    return client.post(url, data=json.dumps(payload), content_type="application/json")


def test_api_erfassung_und_idempotenz(
    installer_device: tuple[Client, User], sensor_a: Sensor, project_a: Project
) -> None:
    client, _ = installer_device
    cid = uuid.uuid4()
    url = reverse("api:installation_create")

    first = _post_json(client, url, _create_payload(sensor_a, project_a, cid))
    assert first.status_code == 201
    body = first.json()
    assert body["dev_eui"] == "AAAAAAAAAAAAAAAA"

    # Erneutes Senden derselben client_uuid ist idempotent (200 statt 201, keine Dublette).
    second = _post_json(client, url, _create_payload(sensor_a, project_a, cid))
    assert second.status_code == 200
    with tenant_context(sensor_a.tenant):
        assert Installation.objects.filter(client_uuid=cid).count() == 1
    assert AuditLog.objects.filter(action=AuditAction.INSTALLATION_CREATED).exists()


def test_api_projekt_ohne_zugang_wird_abgelehnt(
    installer_device: tuple[Client, User], sensor_a: Sensor, tenant_a: Tenant
) -> None:
    client, _ = installer_device
    with tenant_context(tenant_a):
        unassigned = Project.objects.create(number="P-X", name="Nicht zugewiesen", status="active")
    response = _post_json(
        client, reverse("api:installation_create"), _create_payload(sensor_a, unassigned)
    )
    assert response.status_code == 400


def test_api_foto_upload_und_idempotenz(
    installer_device: tuple[Client, User], sensor_a: Sensor, project_a: Project
) -> None:
    client, _ = installer_device
    cid = uuid.uuid4()
    _post_json(
        client, reverse("api:installation_create"), _create_payload(sensor_a, project_a, cid)
    )

    photo_url = reverse("api:installation_photos", args=[cid])
    photo_cid = str(uuid.uuid4())
    image = SimpleUploadedFile("foto.jpg", _image_bytes(), content_type="image/jpeg")
    first = client.post(photo_url, {"image": image, "client_uuid": photo_cid, "order": 0})
    assert first.status_code == 201
    assert "thumbnail_url" in first.json()

    # Idempotenz: gleiche Foto-client_uuid → 200, keine Dublette.
    image2 = SimpleUploadedFile("foto.jpg", _image_bytes(), content_type="image/jpeg")
    second = client.post(photo_url, {"image": image2, "client_uuid": photo_cid, "order": 0})
    assert second.status_code == 200
    with tenant_context(sensor_a.tenant):
        assert InstallationPhoto.objects.count() == 1


def test_api_ungueltiges_bild_wird_abgelehnt(
    installer_device: tuple[Client, User], sensor_a: Sensor, project_a: Project
) -> None:
    client, _ = installer_device
    cid = uuid.uuid4()
    _post_json(
        client, reverse("api:installation_create"), _create_payload(sensor_a, project_a, cid)
    )
    bad = SimpleUploadedFile("x.jpg", b"kein bild", content_type="image/jpeg")
    response = client.post(reverse("api:installation_photos", args=[cid]), {"image": bad})
    assert response.status_code == 400


def test_api_erfordert_authentifizierung(sensor_a: Sensor, project_a: Project) -> None:
    response = _post_json(
        Client(), reverse("api:installation_create"), _create_payload(sensor_a, project_a)
    )
    assert response.status_code in (401, 403)


def test_geschuetztes_foto_zugriff_und_isolation(
    installer_device: tuple[Client, User],
    sensor_a: Sensor,
    project_a: Project,
    admin_a_client: Client,
    admin_b_client: Client,
) -> None:
    client, _ = installer_device
    cid = uuid.uuid4()
    _post_json(
        client, reverse("api:installation_create"), _create_payload(sensor_a, project_a, cid)
    )
    image = SimpleUploadedFile("foto.jpg", _image_bytes(), content_type="image/jpeg")
    client.post(reverse("api:installation_photos", args=[cid]), {"image": image})

    with tenant_context(sensor_a.tenant):
        photo = InstallationPhoto.objects.get()
    media_url = reverse("installations:media", args=[photo.photo_uuid, "thumb"])

    # Administrator desselben Mandanten darf das Foto abrufen.
    ok = admin_a_client.get(media_url)
    assert ok.status_code == 200
    assert ok["Content-Type"] == "image/jpeg"

    # Administrator eines anderen Mandanten nicht (404 statt 403 – kein Rückschluss).
    assert admin_b_client.get(media_url).status_code == 404


def test_api_karte_liefert_aktive_installationen(
    installer_device: tuple[Client, User], sensor_a: Sensor, project_a: Project
) -> None:
    client, _ = installer_device
    _post_json(client, reverse("api:installation_create"), _create_payload(sensor_a, project_a))
    response = client.get(reverse("api:installation_map"))
    assert response.status_code == 200
    points = response.json()
    assert len(points) == 1
    assert points[0]["latitude"] == pytest.approx(47.1)
