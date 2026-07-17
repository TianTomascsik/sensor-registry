"""Tests der zusätzlichen Sicherheits-Header (CSP, Permissions-Policy)."""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db


def _csp(response) -> str:
    return response["Content-Security-Policy"]


def test_csp_wird_gesetzt() -> None:
    response = Client().get(reverse("accounts:login"))
    csp = _csp(response)
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    # OpenStreetMap-Kacheln für die Karte sind erlaubt.
    assert "https://*.tile.openstreetmap.org" in csp


def test_script_src_ist_strikt_ohne_unsafe_inline() -> None:
    csp = _csp(Client().get(reverse("accounts:login")))
    directives = {
        part.strip().split(" ", 1)[0]: part.strip() for part in csp.split(";") if part.strip()
    }
    assert directives["script-src"] == "script-src 'self'"


def test_permissions_policy_erlaubt_geolocation() -> None:
    response = Client().get(reverse("accounts:login"))
    policy = response["Permissions-Policy"]
    assert "geolocation=(self)" in policy
    assert "camera=()" in policy
