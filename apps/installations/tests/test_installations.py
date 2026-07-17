"""Tests der Installations-Services: Idempotenz, Wiedereinbau, Storno, Sichtbarkeit."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditAction, AuditLog
from apps.core.models import Tenant
from apps.core.tenancy import tenant_context
from apps.installations.models import Installation, InstallationStatus
from apps.installations.services import (
    cancel_installation,
    correct_installation,
    create_installation,
    get_visible_installation,
    map_installations,
    visible_installations,
)
from apps.projects.models import Project, ProjectAssignment
from apps.sensors.models import Sensor

pytestmark = pytest.mark.django_db


@pytest.fixture
def sensor_a(tenant_a: Tenant) -> Sensor:
    with tenant_context(tenant_a):
        return Sensor.objects.create(dev_eui="AAAAAAAAAAAAAAAA")


@pytest.fixture
def project_a(tenant_a: Tenant) -> Project:
    with tenant_context(tenant_a):
        return Project.objects.create(number="P-1", name="Projekt", status="active")


@pytest.fixture
def assigned_installer(tenant_a: Tenant, project_a: Project, installer_a: User) -> User:
    with tenant_context(tenant_a):
        ProjectAssignment.objects.create(project=project_a, user=installer_a)
    return installer_a


def _create(tenant, sensor, project, installer, **overrides):
    defaults = {
        "client_uuid": uuid.uuid4(),
        "sensor": sensor,
        "project": project,
        "installer": installer,
        "latitude": Decimal("47.100000"),
        "longitude": Decimal("8.200000"),
        "accuracy_m": 3.0,
        "captured_at": timezone.now(),
        "actor": installer,
    }
    defaults.update(overrides)
    with tenant_context(tenant):
        return create_installation(**defaults)


def test_erfassung_ist_idempotent(
    tenant_a: Tenant, sensor_a: Sensor, project_a: Project, installer_a: User
) -> None:
    cid = uuid.uuid4()
    inst1, created1 = _create(tenant_a, sensor_a, project_a, installer_a, client_uuid=cid)
    inst2, created2 = _create(tenant_a, sensor_a, project_a, installer_a, client_uuid=cid)
    assert created1 is True
    assert created2 is False
    assert inst1.pk == inst2.pk
    with tenant_context(tenant_a):
        assert Installation.objects.count() == 1


def test_wiedereinbau_setzt_alte_installation_auf_ausgebaut(
    tenant_a: Tenant, sensor_a: Sensor, project_a: Project, installer_a: User
) -> None:
    first, _ = _create(tenant_a, sensor_a, project_a, installer_a)
    second, _ = _create(tenant_a, sensor_a, project_a, installer_a)

    first.refresh_from_db()
    second.refresh_from_db()
    assert first.status == InstallationStatus.REMOVED
    assert second.status == InstallationStatus.INSTALLED
    with tenant_context(tenant_a):
        active = Installation.objects.filter(
            sensor=sensor_a, status=InstallationStatus.INSTALLED, cancelled_at__isnull=True
        )
        assert active.count() == 1


def test_partial_unique_verhindert_zwei_aktive_pro_sensor(
    tenant_a: Tenant, sensor_a: Sensor, project_a: Project, installer_a: User
) -> None:
    _create(tenant_a, sensor_a, project_a, installer_a)
    # Direktes Anlegen einer zweiten aktiven Installation (ohne Wiedereinbau-Logik) scheitert.
    with tenant_context(tenant_a), pytest.raises(IntegrityError):
        Installation.objects.create(
            client_uuid=uuid.uuid4(),
            sensor=sensor_a,
            project=project_a,
            installer=installer_a,
            latitude=Decimal("47.1"),
            longitude=Decimal("8.2"),
            accuracy_m=2.0,
            captured_at=timezone.now(),
            status=InstallationStatus.INSTALLED,
        )


def test_erfassung_wird_protokolliert(
    tenant_a: Tenant, sensor_a: Sensor, project_a: Project, installer_a: User
) -> None:
    inst, _ = _create(tenant_a, sensor_a, project_a, installer_a)
    assert AuditLog.objects.filter(
        action=AuditAction.INSTALLATION_CREATED, object_id=str(inst.pk)
    ).exists()


def test_storno_gibt_sensor_frei(
    tenant_a: Tenant, sensor_a: Sensor, project_a: Project, installer_a: User
) -> None:
    inst, _ = _create(tenant_a, sensor_a, project_a, installer_a)
    with tenant_context(tenant_a):
        cancel_installation(inst, reason="falscher Sensor", actor=installer_a)
    inst.refresh_from_db()
    assert inst.is_cancelled
    assert AuditLog.objects.filter(action=AuditAction.INSTALLATION_CANCELLED).exists()
    # Nach dem Storno ist der Sensor wieder frei für eine neue aktive Installation.
    new, created = _create(tenant_a, sensor_a, project_a, installer_a)
    assert created is True


def test_korrektur_aendert_projekt_und_beschreibung(
    tenant_a: Tenant, sensor_a: Sensor, project_a: Project, installer_a: User
) -> None:
    inst, _ = _create(tenant_a, sensor_a, project_a, installer_a)
    with tenant_context(tenant_a):
        other = Project.objects.create(number="P-2", name="Anderes", status="active")
        correct_installation(inst, project=other, description="korrigiert", actor=installer_a)
    inst.refresh_from_db()
    assert inst.project_id == other.pk
    assert inst.description == "korrigiert"
    assert AuditLog.objects.filter(action=AuditAction.INSTALLATION_CORRECTED).exists()


def test_monteur_sieht_nur_zugewiesene_installationen(
    tenant_a: Tenant, sensor_a: Sensor, project_a: Project, assigned_installer: User
) -> None:
    inst, _ = _create(tenant_a, sensor_a, project_a, assigned_installer)
    # Zweites Projekt ohne Zuweisung.
    with tenant_context(tenant_a):
        other_project = Project.objects.create(number="P-9", name="Fremd", status="active")
        other_sensor = Sensor.objects.create(dev_eui="BBBBBBBBBBBBBBBB")
    hidden, _ = _create(tenant_a, other_sensor, other_project, assigned_installer)

    with tenant_context(tenant_a):
        visible = set(visible_installations(assigned_installer).values_list("pk", flat=True))
    assert inst.pk in visible
    assert hidden.pk not in visible


def test_installation_ist_mandantengetrennt(
    tenant_a: Tenant,
    tenant_b: Tenant,
    sensor_a: Sensor,
    project_a: Project,
    installer_a: User,
    admin_b: User,
) -> None:
    inst, _ = _create(tenant_a, sensor_a, project_a, installer_a)
    with tenant_context(tenant_b), pytest.raises(Installation.DoesNotExist):
        get_visible_installation(admin_b, inst.pk)


def test_map_zeigt_nur_aktive(
    tenant_a: Tenant, sensor_a: Sensor, project_a: Project, installer_a: User, admin_a: User
) -> None:
    inst, _ = _create(tenant_a, sensor_a, project_a, installer_a)
    # Als Administrator abfragen (sieht alle Installationen des Mandanten).
    with tenant_context(tenant_a):
        assert inst.pk in set(map_installations(admin_a).values_list("pk", flat=True))
        cancel_installation(inst, reason="x", actor=admin_a)
        assert inst.pk not in set(map_installations(admin_a).values_list("pk", flat=True))
