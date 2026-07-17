"""Service-Layer der Sensoren-App: Verwaltung und CSV-Import.

Der CSV-Import ist bewusst fehlertolerant: gültige, neue Sensoren werden angelegt,
während fehlerhafte oder doppelte Zeilen übersprungen und in einem strukturierten Bericht
zurückgemeldet werden. So lässt sich eine große Sensorliste importieren, ohne dass eine
einzelne fehlerhafte Zeile den gesamten Vorgang abbricht.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, QuerySet
from django.http import HttpRequest

from apps.accounts.models import User
from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.core.tenancy import current_tenant
from apps.sensors.models import DEVEUI_VALIDATOR, Sensor, normalize_deveui

#: Zuordnung tolerant erkannter CSV-Spaltenüberschriften auf die Modellfelder.
#: Schlüssel sind normalisierte Überschriften (klein, ohne Leer-/Unterstriche).
_HEADER_ALIASES: dict[str, str] = {
    "deveui": "dev_eui",
    "eui": "dev_eui",
    "hersteller": "manufacturer",
    "manufacturer": "manufacturer",
    "typ": "sensor_type",
    "type": "sensor_type",
    "sensortyp": "sensor_type",
    "sensortype": "sensor_type",
    "seriennummer": "serial_number",
    "serial": "serial_number",
    "serialnumber": "serial_number",
    "sn": "serial_number",
    "bemerkung": "note",
    "note": "note",
    "notiz": "note",
    "kommentar": "note",
}


@dataclass
class RowError:
    """Ein fehlerhafter Datensatz aus dem CSV-Import."""

    line: int
    value: str
    message: str


@dataclass
class ImportReport:
    """Ergebnis eines CSV-Imports."""

    total_rows: int = 0
    created: int = 0
    skipped_existing: int = 0
    skipped_duplicate: int = 0
    errors: list[RowError] = field(default_factory=list)
    fatal_error: str | None = None

    @property
    def has_fatal_error(self) -> bool:
        return self.fatal_error is not None

    @property
    def error_count(self) -> int:
        return len(self.errors)


def list_sensors(search: str = "") -> QuerySet[Sensor]:
    """Sensoren des aktiven Mandanten, optional gefiltert nach einem Suchbegriff."""
    qs = Sensor.objects.all()
    term = search.strip()
    if term:
        qs = qs.filter(
            Q(dev_eui__icontains=normalize_deveui(term))
            | Q(manufacturer__icontains=term)
            | Q(sensor_type__icontains=term)
            | Q(serial_number__icontains=term)
        )
    return qs


def create_sensor(
    *,
    dev_eui: str,
    manufacturer: str,
    sensor_type: str,
    serial_number: str,
    note: str,
    actor: User,
    request: HttpRequest | None = None,
) -> Sensor:
    """Legt einen einzelnen Sensor an und protokolliert die Aktion."""
    sensor = Sensor.objects.create(
        dev_eui=dev_eui,
        manufacturer=manufacturer,
        sensor_type=sensor_type,
        serial_number=serial_number,
        note=note,
    )
    record(
        AuditAction.SENSOR_CREATED,
        actor=actor,
        obj=sensor,
        changes={"dev_eui": sensor.dev_eui},
        request=request,
    )
    return sensor


def update_sensor(
    sensor: Sensor,
    *,
    manufacturer: str,
    sensor_type: str,
    serial_number: str,
    note: str,
    actor: User,
    request: HttpRequest | None = None,
) -> Sensor:
    """Aktualisiert die Stammdaten eines Sensors (der DevEUI bleibt unveränderlich)."""
    changes: dict[str, dict[str, str]] = {}
    for field_name, new in (
        ("manufacturer", manufacturer),
        ("sensor_type", sensor_type),
        ("serial_number", serial_number),
        ("note", note),
    ):
        old = getattr(sensor, field_name)
        if old != new:
            changes[field_name] = {"von": old, "zu": new}
            setattr(sensor, field_name, new)
    if changes:
        sensor.save(update_fields=list(changes.keys()))
        record(
            AuditAction.SENSOR_UPDATED,
            actor=actor,
            obj=sensor,
            changes=changes,
            request=request,
        )
    return sensor


def delete_sensor(sensor: Sensor, *, actor: User, request: HttpRequest | None = None) -> None:
    """Löscht einen Sensor und protokolliert die Aktion."""
    dev_eui = sensor.dev_eui
    record(
        AuditAction.SENSOR_DELETED,
        actor=actor,
        obj=sensor,
        changes={"dev_eui": dev_eui},
        request=request,
    )
    sensor.delete()


def import_sensors_from_csv(
    *, data: bytes, actor: User, request: HttpRequest | None = None
) -> ImportReport:
    """Importiert Sensoren aus CSV-Rohdaten.

    Erkennt Kodierung (inkl. BOM) und Trennzeichen automatisch. Nur der DevEUI ist Pflicht;
    alle übrigen Spalten sind optional. Gültige, noch nicht vorhandene Sensoren werden
    angelegt; doppelte oder fehlerhafte Zeilen erscheinen im Bericht.
    """
    report = ImportReport()

    text = _decode(data)
    if text is None:
        report.fatal_error = "Die Datei konnte nicht als UTF-8 gelesen werden."
        return report

    try:
        reader = _make_reader(text)
    except ValueError as exc:
        report.fatal_error = str(exc)
        return report

    if reader.fieldnames is None:
        report.fatal_error = "Die Datei enthält keine Kopfzeile."
        return report

    column_map = _map_columns(reader.fieldnames)
    if "dev_eui" not in column_map.values():
        report.fatal_error = "Es wurde keine DevEUI-Spalte gefunden."
        return report

    tenant = current_tenant()
    existing: set[str] = set(Sensor.objects.values_list("dev_eui", flat=True))
    seen_in_file: set[str] = set()
    to_create: list[Sensor] = []

    for line_number, raw_row in enumerate(reader, start=2):  # Zeile 1 = Kopfzeile
        report.total_rows += 1
        values = _extract_values(raw_row, column_map)
        raw_deveui = values["dev_eui"]
        dev_eui = normalize_deveui(raw_deveui)

        try:
            DEVEUI_VALIDATOR(dev_eui)
        except ValidationError:
            report.errors.append(
                RowError(line_number, raw_deveui, "Ungültiger DevEUI (16 Hexzeichen erwartet).")
            )
            continue

        if dev_eui in existing:
            report.skipped_existing += 1
            continue
        if dev_eui in seen_in_file:
            report.skipped_duplicate += 1
            continue

        seen_in_file.add(dev_eui)
        to_create.append(
            Sensor(
                tenant=tenant,
                dev_eui=dev_eui,
                manufacturer=values["manufacturer"],
                sensor_type=values["sensor_type"],
                serial_number=values["serial_number"],
                note=values["note"],
            )
        )

    if to_create:
        with transaction.atomic():
            Sensor.objects.bulk_create(to_create)
        report.created = len(to_create)

    record(
        AuditAction.SENSOR_IMPORTED,
        actor=actor,
        tenant=tenant,
        changes={
            "angelegt": report.created,
            "uebersprungen_vorhanden": report.skipped_existing,
            "uebersprungen_doppelt": report.skipped_duplicate,
            "fehlerhaft": report.error_count,
        },
        request=request,
    )
    return report


def _decode(data: bytes) -> str | None:
    """Dekodiert CSV-Rohdaten als UTF-8 (BOM-tolerant)."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


def _make_reader(text: str) -> csv.DictReader[str]:
    """Erzeugt einen DictReader mit automatisch erkanntem Trennzeichen."""
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        delimiter = dialect.delimiter
    except csv.Error:
        # Fällt auf Semikolon zurück, wenn im Beispiel vorhanden (deutsches Excel), sonst Komma.
        delimiter = ";" if ";" in sample and "," not in sample else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError("Die Datei enthält keine Kopfzeile.")
    return reader


def _normalize_header(header: str) -> str:
    """Normalisiert eine Spaltenüberschrift für den Abgleich mit den Aliassen."""
    cleaned = header.strip().lower()
    for separator in (" ", "_", "-", "."):
        cleaned = cleaned.replace(separator, "")
    return cleaned


def _map_columns(fieldnames: Sequence[str]) -> dict[str, str]:
    """Bildet die tatsächlichen CSV-Überschriften auf Modellfelder ab."""
    mapping: dict[str, str] = {}
    for name in fieldnames:
        if name is None:
            continue
        target = _HEADER_ALIASES.get(_normalize_header(name))
        if target is not None:
            mapping[name] = target
    return mapping


def _extract_values(row: dict[str, str], column_map: dict[str, str]) -> dict[str, str]:
    """Liest die Werte einer Zeile in die Modellfelder (fehlende Felder werden leer)."""
    values = {
        "dev_eui": "",
        "manufacturer": "",
        "sensor_type": "",
        "serial_number": "",
        "note": "",
    }
    for source_col, target in column_map.items():
        raw = row.get(source_col)
        if raw is not None:
            values[target] = raw.strip()
    return values
