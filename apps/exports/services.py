"""Service-Layer der Exporte.

Baut aus Installationen die je Format passende Datenstruktur, ruft den Formatierer auf und
protokolliert jeden Export im Audit-Log.
"""

from __future__ import annotations

import base64
from collections.abc import Iterable
from typing import Any

from django.template.loader import render_to_string
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.exports import formats
from apps.exports.formats import ExportFile
from apps.installations.models import Installation

#: Unterstützte Exportformate.
FORMATS = ("csv", "xlsx", "pdf", "gpx", "kml")

_HEADERS = [
    "DevEUI",
    "Projektnummer",
    "Projekt",
    "Monteur",
    "Breitengrad",
    "Längengrad",
    "Genauigkeit (m)",
    "Erfasst am",
    "Status",
    "Beschreibung",
]


def _status_text(installation: Installation) -> str:
    if installation.is_cancelled:
        return "Storniert"
    return installation.get_status_display()


def _rows(installations: list[Installation]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for inst in installations:
        rows.append(
            [
                inst.sensor.dev_eui,
                inst.project.number,
                inst.project.name,
                inst.installer.full_name,
                float(inst.latitude),
                float(inst.longitude),
                round(inst.accuracy_m, 1),
                timezone.localtime(inst.received_at).strftime("%Y-%m-%d %H:%M"),
                _status_text(inst),
                inst.description,
            ]
        )
    return rows


def _points(installations: list[Installation]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for inst in installations:
        desc = f"{inst.project.number} · {inst.description}".strip(" ·")
        points.append(
            {
                "lat": float(inst.latitude),
                "lon": float(inst.longitude),
                "name": inst.sensor.dev_eui,
                "desc": desc,
                "time": inst.received_at.isoformat(),
            }
        )
    return points


def _thumbnail_data_uri(installation: Installation) -> str | None:
    photo = installation.photos.first()
    if photo is None:
        return None
    try:
        with photo.thumbnail.open("rb") as handle:
            encoded = base64.b64encode(handle.read()).decode("ascii")
    except (FileNotFoundError, ValueError, OSError):
        return None
    return f"data:image/jpeg;base64,{encoded}"


def _pdf_report(title: str, installations: list[Installation]) -> ExportFile:
    items = [
        {"installation": inst, "status": _status_text(inst), "thumb": _thumbnail_data_uri(inst)}
        for inst in installations
    ]
    html = render_to_string(
        "exports/report.html",
        {"title": title, "items": items, "generated": timezone.localtime()},
    )
    return formats.to_pdf(html)


def export_installations(
    installations: Iterable[Installation],
    fmt: str,
    *,
    title: str,
    actor: User,
    request: Any | None = None,
) -> ExportFile:
    """Exportiert Installationen im gewünschten Format und protokolliert den Export."""
    if fmt not in FORMATS:
        raise ValueError(f"Unbekanntes Format: {fmt}")
    items = list(installations)

    if fmt == "csv":
        export = formats.to_csv(_HEADERS, _rows(items))
    elif fmt == "xlsx":
        export = formats.to_xlsx(_HEADERS, _rows(items), title)
    elif fmt == "gpx":
        export = formats.to_gpx(_points(items))
    elif fmt == "kml":
        export = formats.to_kml(_points(items), title)
    else:  # pdf
        export = _pdf_report(title, items)

    record(
        AuditAction.EXPORT_CREATED,
        actor=actor,
        changes={"format": fmt, "anzahl": len(items), "titel": title},
        request=request,
    )
    return export
