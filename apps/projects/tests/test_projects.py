"""Tests der Projekte: Mandanten-Isolation, CRUD, Sichtbarkeit und Zuweisungen."""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.audit.models import AuditAction, AuditLog
from apps.core.models import Tenant
from apps.core.tenancy import tenant_context
from apps.projects.models import Project, ProjectAssignment, ProjectStatus

pytestmark = pytest.mark.django_db


def _make_project(tenant: Tenant, number: str = "P-1", name: str = "Projekt") -> Project:
    with tenant_context(tenant):
        return Project.objects.create(number=number, name=name, status=ProjectStatus.ACTIVE)


# --- Mandanten-Isolation an echten Modellen ---------------------------------------


def test_projektnummer_pro_mandant_eindeutig_aber_mandantenuebergreifend_erlaubt(
    tenant_a: Tenant, tenant_b: Tenant
) -> None:
    _make_project(tenant_a, number="P-100", name="A")
    # Gleiche Nummer in anderem Mandanten ist erlaubt ...
    _make_project(tenant_b, number="P-100", name="B")

    with tenant_context(tenant_a):
        assert Project.objects.count() == 1
        assert Project.objects.get().name == "A"
    with tenant_context(tenant_b):
        assert Project.objects.count() == 1
        assert Project.objects.get().name == "B"


def test_doppelte_projektnummer_im_selben_mandanten_scheitert(tenant_a: Tenant) -> None:
    from django.db import IntegrityError

    _make_project(tenant_a, number="P-1")
    with tenant_context(tenant_a):
        with pytest.raises(IntegrityError):
            Project.objects.create(number="P-1", name="Doppelt")


def test_admin_sieht_fremdes_projekt_nicht(admin_a_client: Client, tenant_b: Tenant) -> None:
    foreign = _make_project(tenant_b, number="B-1")
    assert admin_a_client.get(reverse("projects:detail", args=[foreign.pk])).status_code == 404
    assert admin_a_client.get(reverse("projects:update", args=[foreign.pk])).status_code == 404


# --- CRUD --------------------------------------------------------------------------


def test_admin_legt_projekt_an(admin_a_client: Client, tenant_a: Tenant) -> None:
    response = admin_a_client.post(
        reverse("projects:create"),
        {
            "number": "2026-001",
            "name": "Feldtest Nord",
            "customer": "Stadtwerke",
            "description": "Bodenfeuchte",
            "status": ProjectStatus.ACTIVE,
        },
    )
    assert response.status_code == 302
    with tenant_context(tenant_a):
        project = Project.objects.get(number="2026-001")
        assert project.tenant_id == tenant_a.pk
    assert AuditLog.objects.filter(
        action=AuditAction.PROJECT_CREATED, object_id=str(project.pk)
    ).exists()


def test_doppelte_nummer_wird_im_formular_abgelehnt(
    admin_a_client: Client, tenant_a: Tenant
) -> None:
    _make_project(tenant_a, number="X-1")
    response = admin_a_client.post(
        reverse("projects:create"),
        {"number": "X-1", "name": "Zweitversuch", "status": ProjectStatus.ACTIVE},
    )
    assert response.status_code == 200
    with tenant_context(tenant_a):
        assert Project.objects.filter(name="Zweitversuch").count() == 0


def test_admin_aktualisiert_projekt(admin_a_client: Client, tenant_a: Tenant) -> None:
    project = _make_project(tenant_a, number="U-1", name="Alt")
    response = admin_a_client.post(
        reverse("projects:update", args=[project.pk]),
        {"number": "U-1", "name": "Neu", "status": ProjectStatus.COMPLETED},
    )
    assert response.status_code == 302
    project.refresh_from_db()
    assert project.name == "Neu"
    assert project.status == ProjectStatus.COMPLETED


# --- Sichtbarkeit für Monteure -----------------------------------------------------


def test_monteur_sieht_nur_zugewiesene_projekte(
    installer_a_client: Client, installer_a: User, tenant_a: Tenant
) -> None:
    assigned = _make_project(tenant_a, number="Z-1", name="Zugewiesen")
    _make_project(tenant_a, number="Z-2", name="Nicht zugewiesen")
    with tenant_context(tenant_a):
        ProjectAssignment.objects.create(project=assigned, user=installer_a)

    response = installer_a_client.get(reverse("projects:list"))
    assert response.status_code == 200
    visible = {p.pk for p in response.context["projects"]}
    assert assigned.pk in visible
    assert len(visible) == 1


def test_monteur_kann_nicht_zugewiesenes_projekt_nicht_oeffnen(
    installer_a_client: Client, tenant_a: Tenant
) -> None:
    project = _make_project(tenant_a, number="G-1")
    assert installer_a_client.get(reverse("projects:detail", args=[project.pk])).status_code == 404


def test_monteur_darf_projekte_nicht_verwalten(installer_a_client: Client) -> None:
    assert installer_a_client.get(reverse("projects:create")).status_code == 403


# --- Zuweisungen -------------------------------------------------------------------


def test_admin_weist_benutzer_zu_und_entfernt_wieder(
    admin_a_client: Client, installer_a: User, tenant_a: Tenant
) -> None:
    project = _make_project(tenant_a, number="A-1")

    admin_a_client.post(reverse("projects:assign", args=[project.pk]), {"user": installer_a.pk})
    with tenant_context(tenant_a):
        assert ProjectAssignment.objects.filter(project=project, user=installer_a).exists()
    assert AuditLog.objects.filter(action=AuditAction.PROJECT_ASSIGNED).exists()

    admin_a_client.post(reverse("projects:unassign", args=[project.pk, installer_a.pk]))
    with tenant_context(tenant_a):
        assert not ProjectAssignment.objects.filter(project=project, user=installer_a).exists()
    assert AuditLog.objects.filter(action=AuditAction.PROJECT_UNASSIGNED).exists()


def test_zuweisung_ist_idempotent(
    admin_a_client: Client, installer_a: User, tenant_a: Tenant
) -> None:
    project = _make_project(tenant_a, number="I-1")
    url = reverse("projects:assign", args=[project.pk])
    admin_a_client.post(url, {"user": installer_a.pk})
    admin_a_client.post(url, {"user": installer_a.pk})
    with tenant_context(tenant_a):
        assert ProjectAssignment.objects.filter(project=project, user=installer_a).count() == 1


def test_suche_filtert_projekte(admin_a_client: Client, tenant_a: Tenant) -> None:
    _make_project(tenant_a, number="S-1", name="Bodensensor Wald")
    _make_project(tenant_a, number="S-2", name="Klimastation")
    response = admin_a_client.get(reverse("projects:list"), {"q": "Wald"})
    names = {p.name for p in response.context["projects"]}
    assert names == {"Bodensensor Wald"}
