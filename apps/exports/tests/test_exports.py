"""Tests der Exporte: alle Formate, Isolation, Audit und Berechtigungen."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditAction, AuditLog
from apps.core.models import Tenant
from apps.core.tenancy import tenant_context
from apps.installations.services import create_installation
from apps.projects.models import Project
from apps.sensors.models import Sensor

pytestmark = pytest.mark.django_db


@pytest.fixture
def project_with_installation(tenant_a: Tenant, installer_a: User):
    with tenant_context(tenant_a):
        project = Project.objects.create(number="P-1", name="Feldtest", status="active")
        sensor = Sensor.objects.create(dev_eui="70B3D57ED0012345")
        create_installation(
            client_uuid=uuid.uuid4(),
            sensor=sensor,
            project=project,
            installer=installer_a,
            latitude=Decimal("47.100000"),
            longitude=Decimal("8.200000"),
            accuracy_m=3.0,
            captured_at=timezone.now(),
            description="Bodensensor am Waldrand",
            actor=installer_a,
        )
    return project


@pytest.mark.parametrize(
    ("fmt", "content_type", "marker"),
    [
        ("csv", "text/csv", b"70B3D57ED0012345"),
        ("xlsx", "application/vnd.openxmlformats", b"PK"),  # xlsx ist ein ZIP
        ("gpx", "application/gpx+xml", b"<wpt"),
        ("kml", "application/vnd.google-earth.kml+xml", b"<Placemark>"),
        ("pdf", "application/pdf", b"%PDF-"),
    ],
)
def test_projektexport_liefert_jedes_format(
    admin_a_client: Client, project_with_installation: Project, fmt, content_type, marker
) -> None:
    url = reverse("exports:project", args=[project_with_installation.pk])
    response = admin_a_client.get(url, {"format": fmt})
    assert response.status_code == 200
    assert response["Content-Type"].startswith(content_type)
    assert "attachment" in response["Content-Disposition"]
    assert f".{fmt}" in response["Content-Disposition"]
    assert marker in response.getvalue()


def test_export_wird_protokolliert(
    admin_a_client: Client, project_with_installation: Project
) -> None:
    admin_a_client.get(
        reverse("exports:project", args=[project_with_installation.pk]), {"format": "csv"}
    )
    entry = AuditLog.objects.filter(action=AuditAction.EXPORT_CREATED).first()
    assert entry is not None
    assert entry.changes["format"] == "csv"
    assert entry.changes["anzahl"] == 1


def test_unbekanntes_format_ist_404(
    admin_a_client: Client, project_with_installation: Project
) -> None:
    response = admin_a_client.get(
        reverse("exports:project", args=[project_with_installation.pk]), {"format": "docx"}
    )
    assert response.status_code == 404


def test_fremdes_projekt_kann_nicht_exportiert_werden(
    admin_a_client: Client, tenant_b: Tenant
) -> None:
    with tenant_context(tenant_b):
        foreign = Project.objects.create(number="B-1", name="Fremd", status="active")
    response = admin_a_client.get(reverse("exports:project", args=[foreign.pk]), {"format": "csv"})
    assert response.status_code == 404


def test_monteur_darf_nicht_exportieren(
    installer_a: User, project_with_installation: Project
) -> None:
    client = Client()
    client.force_login(installer_a)
    response = client.get(
        reverse("exports:project", args=[project_with_installation.pk]), {"format": "csv"}
    )
    assert response.status_code == 403


def test_suchexport_mit_filter(admin_a_client: Client, project_with_installation: Project) -> None:
    response = admin_a_client.get(reverse("exports:search"), {"format": "csv", "q": "Waldrand"})
    assert response.status_code == 200
    assert b"70B3D57ED0012345" in response.getvalue()
