"""Views der Progressive Web App: Manifest und Service Worker.

Der Service Worker wird serverseitig gerendert, damit die Precache-Liste und die
Cache-Version aus den (in Produktion gehashten) Static-Dateien abgeleitet werden können.
So aktualisiert sich der Cache automatisch, sobald sich Assets ändern.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.cache import never_cache

# Statische Assets, die für den Offline-Betrieb des Erfassungsflusses vorab zwischengespeichert
# werden. Reihenfolge ist unerheblich; die Liste bestimmt die Cache-Version.
_PRECACHE_STATIC = [
    "css/app.css",
    "vendor/bootstrap/bootstrap.min.css",
    "vendor/bootstrap/bootstrap.bundle.min.js",
    "vendor/bootstrap-icons/bootstrap-icons.min.css",
    "vendor/bootstrap-icons/fonts/bootstrap-icons.woff2",
    "js/capture.js",
    "js/map.js",
    "js/pwa/idb.js",
    "js/pwa/outbox.js",
    "js/pwa/register.js",
    "img/icon-192.png",
]


def _precache_asset_urls() -> list[str]:
    """Öffentliche URLs der vorab zu cachenden statischen Assets (ggf. gehasht)."""
    return [static(path) for path in _PRECACHE_STATIC]


def _shell_page_urls() -> list[str]:
    """App-Seiten, die für den Offline-Betrieb (best effort) gecacht werden."""
    return [reverse("installations:capture"), reverse("core:dashboard")]


def _cache_fingerprint(assets: list[str], pages: list[str]) -> str:
    """Grundlage der Cache-Version.

    In Produktion sind die Asset-URLs gehasht – Inhaltsänderungen schlagen sich bereits in der
    URL nieder, sodass die Version automatisch wechselt. In der Entwicklung sind die URLs
    stabil; damit der Service Worker nach jeder Asset-Änderung dennoch erneuert wird (statt
    veraltetes JavaScript cache-first auszuliefern), fließen dort zusätzlich die
    Änderungszeiten der Quelldateien ein.
    """
    parts = [*assets, *pages]
    if settings.DEBUG:
        for path in _PRECACHE_STATIC:
            absolute = finders.find(path)
            if absolute:
                parts.append(f"{path}:{Path(absolute).stat().st_mtime_ns}")
    return "\n".join(parts)


def manifest(request: HttpRequest) -> JsonResponse:
    """Liefert das Web-App-Manifest."""
    data = {
        "name": "Sensor-Dokumentation",
        "short_name": "Sensoren",
        "description": "Dokumentation von LoRaWAN-Bodensensor-Installationen",
        "start_url": reverse("installations:capture"),
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#f8f9fa",
        "theme_color": "#0d6efd",
        "lang": "de",
        "icons": [
            {"src": static("img/icon-192.png"), "sizes": "192x192", "type": "image/png"},
            {"src": static("img/icon-512.png"), "sizes": "512x512", "type": "image/png"},
            {
                "src": static("img/icon-maskable-512.png"),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
        ],
    }
    return JsonResponse(data)


@never_cache
def service_worker(request: HttpRequest) -> HttpResponse:
    """Rendert den Service Worker (mit Precache-Liste und Cache-Version) im Root-Scope."""
    assets = _precache_asset_urls()
    pages = _shell_page_urls()
    # Cache-Version aus Precache-Liste (und in DEBUG den Datei-Änderungszeiten) ableiten:
    # ändern sich Assets, ändert sich die Version und der Service Worker erneuert den Cache.
    fingerprint = _cache_fingerprint(assets, pages)
    cache_version = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:12]

    from django.template.loader import render_to_string

    body = render_to_string(
        "pwa/sw.js",
        {
            "cache_version": cache_version,
            "precache_assets_json": json.dumps(assets),
            "precache_pages_json": json.dumps(pages),
            "api_prefix": "/api/",
            "media_prefix": reverse("installations:list").rstrip("/") + "/medien/",
        },
    )
    response = HttpResponse(body, content_type="text/javascript")
    # Root-Scope erlauben und Auslieferung nicht cachen (sonst hängen SW-Updates).
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response
