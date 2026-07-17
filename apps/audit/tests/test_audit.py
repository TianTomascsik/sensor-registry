"""Tests des Audit-Service."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from apps.audit.models import AuditAction, AuditLog
from apps.audit.services import client_ip, record
from apps.core.models import Tenant

pytestmark = pytest.mark.django_db


def test_record_leitet_mandant_aus_objekt_ab(tenant_a: Tenant) -> None:
    entry = record(AuditAction.TENANT_UPDATED, obj=tenant_a)
    assert entry.tenant_id == tenant_a.pk
    assert entry.object_type == "Tenant"
    assert entry.object_id == str(tenant_a.pk)
    assert entry.object_repr == str(tenant_a)


def test_record_erfasst_ip_und_user_agent() -> None:
    request = RequestFactory().post(
        "/", HTTP_USER_AGENT="TestAgent/1.0", HTTP_X_FORWARDED_FOR="203.0.113.7, 10.0.0.1"
    )
    entry = record(AuditAction.LOGIN_FAILED, request=request, changes={"email": "x@y.z"})
    # Erster Eintrag der Weiterleitungskette = ursprünglicher Client.
    assert entry.ip_address == "203.0.113.7"
    assert entry.user_agent == "TestAgent/1.0"
    assert entry.changes == {"email": "x@y.z"}


def test_client_ip_ohne_proxy_header() -> None:
    request = RequestFactory().get("/", REMOTE_ADDR="198.51.100.5")
    assert client_ip(request) == "198.51.100.5"


def test_audit_ist_nach_zeit_absteigend_sortiert(tenant_a: Tenant) -> None:
    first = record(AuditAction.TENANT_CREATED, obj=tenant_a)
    second = record(AuditAction.TENANT_UPDATED, obj=tenant_a)
    ordered = list(AuditLog.objects.all())
    assert ordered.index(second) < ordered.index(first)
