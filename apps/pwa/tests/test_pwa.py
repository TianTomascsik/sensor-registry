"""Tests der PWA-Server-Verträge: Manifest und Service Worker."""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_manifest_wird_ausgeliefert() -> None:
    response = Client().get(reverse("manifest"))
    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/json")
    data = response.json()
    assert data["name"]
    assert data["display"] == "standalone"
    assert data["start_url"] == reverse("installations:capture")
    assert any(icon["sizes"] == "512x512" for icon in data["icons"])
    assert any(icon.get("purpose") == "maskable" for icon in data["icons"])


def test_service_worker_header_und_inhalt() -> None:
    response = Client().get(reverse("service_worker"))
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/javascript")
    assert response["Service-Worker-Allowed"] == "/"
    assert "no-cache" in response["Cache-Control"]

    body = response.content.decode("utf-8")
    # Cache-Version und Precache-Liste sind eingebettet.
    assert "papa-" in body
    assert "capture.js" in body
    assert reverse("installations:capture") in body
