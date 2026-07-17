"""Tests der Mandanten-Durchsetzung (fail-closed).

Da in Phase 1 noch kein Fachmodell mandantengebunden ist, wird die Durchsetzung am
Hilfsmodell :class:`apps.testsupport.models.ScopedThing` geprüft (nur unter den
Test-Einstellungen geladen). Ab Phase 2 kommen Isolationstests an echten Modellen
(Projekte, Sensoren, Installationen) hinzu.
"""

from __future__ import annotations

import pytest

from apps.core.models import Tenant
from apps.core.tenancy import (
    TenantContextMissing,
    TenantManager,
    TenantScopeViolation,
    current_tenant,
    current_tenant_or_none,
    is_system_context,
    system_context,
    tenant_context,
)
from apps.testsupport.models import ScopedThing

pytestmark = pytest.mark.django_db


def test_zugriff_ohne_kontext_schlaegt_hart_fehl() -> None:
    # Fail-closed: ohne Mandantenkontext darf keine Zeile geliefert werden.
    with pytest.raises(TenantContextMissing):
        list(ScopedThing.objects.all())


def test_filtert_auf_aktiven_mandanten(tenant_a: Tenant, tenant_b: Tenant) -> None:
    with tenant_context(tenant_a):
        ScopedThing.objects.create(name="A1")
        ScopedThing.objects.create(name="A2")
    with tenant_context(tenant_b):
        ScopedThing.objects.create(name="B1")

    with tenant_context(tenant_a):
        assert set(ScopedThing.objects.values_list("name", flat=True)) == {"A1", "A2"}
    with tenant_context(tenant_b):
        assert set(ScopedThing.objects.values_list("name", flat=True)) == {"B1"}


def test_systemkontext_sieht_alle(tenant_a: Tenant, tenant_b: Tenant) -> None:
    with tenant_context(tenant_a):
        ScopedThing.objects.create(name="A1")
    with tenant_context(tenant_b):
        ScopedThing.objects.create(name="B1")

    with system_context():
        assert ScopedThing.objects.count() == 2
        assert is_system_context() is True


def test_save_injiziert_mandanten_aus_kontext(tenant_a: Tenant) -> None:
    with tenant_context(tenant_a):
        thing = ScopedThing.objects.create(name="ohne-expliziten-mandanten")
        assert thing.tenant_id == tenant_a.pk


def test_save_verhindert_cross_tenant_write(tenant_a: Tenant, tenant_b: Tenant) -> None:
    # Ein Objekt von Mandant B darf nicht im Kontext von Mandant A gespeichert werden.
    with tenant_context(tenant_b):
        thing = ScopedThing.objects.create(name="gehoert-zu-b")

    thing.name = "manipuliert"
    with tenant_context(tenant_a):
        with pytest.raises(TenantScopeViolation):
            thing.save()


def test_save_ohne_kontext_schlaegt_fehl() -> None:
    thing = ScopedThing(name="heimatlos")
    with pytest.raises(TenantContextMissing):
        thing.save()


def test_related_manager_bleibt_gefiltert(tenant_a: Tenant, tenant_b: Tenant) -> None:
    with tenant_context(tenant_a):
        ScopedThing.objects.create(name="A1")
    with tenant_context(tenant_b):
        ScopedThing.objects.create(name="B1")

    # Der über die Rückbeziehung erreichbare Manager ist ebenfalls mandantengefiltert.
    with tenant_context(tenant_a):
        assert list(tenant_a.scopedthings.values_list("name", flat=True)) == ["A1"]


def test_unscoped_manager_umgeht_filter(tenant_a: Tenant, tenant_b: Tenant) -> None:
    with tenant_context(tenant_a):
        ScopedThing.objects.create(name="A1")
    with tenant_context(tenant_b):
        ScopedThing.objects.create(name="B1")

    # Der ungefilterte Manager (für Djangos interne Operationen) sieht alles – ohne Kontext.
    assert ScopedThing.unscoped.count() == 2


def test_current_tenant_helpers(tenant_a: Tenant) -> None:
    with tenant_context(tenant_a):
        assert current_tenant() == tenant_a
        assert current_tenant_or_none() == tenant_a
    with system_context():
        assert current_tenant_or_none() is None
        with pytest.raises(TenantContextMissing):
            current_tenant()


def test_manager_ist_tenant_manager() -> None:
    from django.db.models import Manager

    # Standard-Manager filtert (TenantManager) ...
    assert isinstance(ScopedThing.objects, TenantManager)
    assert isinstance(ScopedThing._default_manager, TenantManager)
    # ... der Base-Manager (für Djangos interne Operationen) bleibt jedoch ungefiltert.
    # Kinder erben ihn über die abstrakte Basisklasse, auch mit eigener Meta-Klasse.
    assert type(ScopedThing._base_manager) is Manager
    assert ScopedThing._base_manager.name == "unscoped"
