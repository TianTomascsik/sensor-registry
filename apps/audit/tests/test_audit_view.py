"""Tests der Audit-Log-Ansicht (Superadmin, filterbar, mandantengetrennt)."""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.core.middleware import ACTIVE_TENANT_SESSION_KEY
from apps.core.models import Tenant

pytestmark = pytest.mark.django_db


@pytest.fixture
def entries(tenant_a: Tenant, tenant_b: Tenant):
    record(AuditAction.PROJECT_CREATED, tenant=tenant_a, changes={"x": 1})
    record(AuditAction.EXPORT_CREATED, tenant=tenant_a, changes={"format": "csv"})
    record(AuditAction.PROJECT_CREATED, tenant=tenant_b, changes={"x": 2})


def test_superadmin_sieht_audit_log(superadmin_client: Client, entries: None) -> None:
    response = superadmin_client.get(reverse("audit:list"))
    assert response.status_code == 200
    assert response.context["page_obj"].paginator.count >= 3


def test_filter_nach_aktion(superadmin_client: Client, entries: None) -> None:
    response = superadmin_client.get(
        reverse("audit:list"), {"action": AuditAction.EXPORT_CREATED.value}
    )
    actions = {e.action for e in response.context["entries"]}
    assert actions == {AuditAction.EXPORT_CREATED.value}


def test_mandanten_umschalter_grenzt_ein(
    superadmin_client: Client, entries: None, tenant_b: Tenant
) -> None:
    session = superadmin_client.session
    session[ACTIVE_TENANT_SESSION_KEY] = tenant_b.pk
    session.save()
    response = superadmin_client.get(reverse("audit:list"))
    tenants = {e.tenant_id for e in response.context["entries"]}
    assert tenants == {tenant_b.pk}


def test_mandantenadmin_hat_keinen_zugriff(admin_a_client: Client) -> None:
    assert admin_a_client.get(reverse("audit:list")).status_code == 403
