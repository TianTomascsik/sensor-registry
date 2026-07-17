"""Formulare der Sensoren-App."""

from __future__ import annotations

from typing import Any

from django import forms

from apps.sensors.models import DEVEUI_VALIDATOR, Sensor, normalize_deveui

_TEXT = {"class": "form-control form-control-lg"}
_AREA = {"class": "form-control form-control-lg", "rows": 3}

#: Obergrenze für CSV-Uploads (großzügig für Sensorlisten, aber gegen Missbrauch begrenzt).
MAX_CSV_BYTES = 5 * 1024 * 1024


class SensorCreateForm(forms.Form):
    """Anlegen eines einzelnen Sensors."""

    dev_eui = forms.CharField(
        label="DevEUI",
        max_length=32,
        widget=forms.TextInput(attrs=_TEXT),
        help_text="16 Hexadezimalzeichen; Trennzeichen werden automatisch entfernt.",
    )
    manufacturer = forms.CharField(
        label="Hersteller", max_length=120, required=False, widget=forms.TextInput(attrs=_TEXT)
    )
    sensor_type = forms.CharField(
        label="Typ", max_length=120, required=False, widget=forms.TextInput(attrs=_TEXT)
    )
    serial_number = forms.CharField(
        label="Seriennummer", max_length=120, required=False, widget=forms.TextInput(attrs=_TEXT)
    )
    note = forms.CharField(label="Bemerkung", required=False, widget=forms.Textarea(attrs=_AREA))

    def clean_dev_eui(self) -> str:
        dev_eui = normalize_deveui(self.cleaned_data["dev_eui"])
        DEVEUI_VALIDATOR(dev_eui)
        if Sensor.objects.filter(dev_eui=dev_eui).exists():
            raise forms.ValidationError("Ein Sensor mit diesem DevEUI existiert bereits.")
        return dev_eui


class SensorUpdateForm(forms.Form):
    """Bearbeiten der Stammdaten eines Sensors (DevEUI bleibt unveränderlich)."""

    manufacturer = forms.CharField(
        label="Hersteller", max_length=120, required=False, widget=forms.TextInput(attrs=_TEXT)
    )
    sensor_type = forms.CharField(
        label="Typ", max_length=120, required=False, widget=forms.TextInput(attrs=_TEXT)
    )
    serial_number = forms.CharField(
        label="Seriennummer", max_length=120, required=False, widget=forms.TextInput(attrs=_TEXT)
    )
    note = forms.CharField(label="Bemerkung", required=False, widget=forms.Textarea(attrs=_AREA))


class SensorImportForm(forms.Form):
    """Upload einer CSV-Datei zum Sensorimport."""

    file = forms.FileField(
        label="CSV-Datei",
        widget=forms.ClearableFileInput(
            attrs={"class": "form-control form-control-lg", "accept": ".csv,text/csv"}
        ),
        help_text="Erwartet eine Kopfzeile mit mindestens einer DevEUI-Spalte. "
        "Erkannt werden u. a. die Spalten DevEUI, Hersteller, Typ, Seriennummer, Bemerkung.",
    )

    def clean_file(self) -> Any:
        upload = self.cleaned_data["file"]
        if upload.size > MAX_CSV_BYTES:
            raise forms.ValidationError("Die Datei ist zu groß (maximal 5 MB).")
        name = (upload.name or "").lower()
        if not name.endswith(".csv"):
            raise forms.ValidationError("Bitte eine Datei mit der Endung .csv hochladen.")
        return upload
