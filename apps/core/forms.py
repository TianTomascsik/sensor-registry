"""Formulare der Kern-App: Mandantenverwaltung."""

from __future__ import annotations

from typing import Any

from django import forms
from django.utils.text import slugify

from apps.core.models import Tenant

_TEXT = {"class": "form-control form-control-lg"}
_NUMBER = {"class": "form-control form-control-lg", "min": 1}


class TenantCreateForm(forms.Form):
    """Anlegen eines Mandanten."""

    name = forms.CharField(label="Name", max_length=200, widget=forms.TextInput(attrs=_TEXT))
    slug = forms.SlugField(
        label="Kürzel",
        max_length=60,
        widget=forms.TextInput(attrs=_TEXT),
        help_text="Eindeutiges Kürzel (Kleinbuchstaben, Ziffern, Bindestrich). "
        "Wird u. a. für die Medienverzeichnisse verwendet und ist unveränderlich.",
    )
    gps_accuracy_threshold_m = forms.IntegerField(
        label="GPS-Genauigkeitsgrenze (Meter)",
        min_value=1,
        initial=5,
        widget=forms.NumberInput(attrs=_NUMBER),
    )

    def clean_slug(self) -> str:
        slug = slugify(self.cleaned_data["slug"])
        if not slug:
            raise forms.ValidationError("Bitte ein gültiges Kürzel angeben.")
        if Tenant.objects.filter(slug=slug).exists():
            raise forms.ValidationError("Dieses Kürzel ist bereits vergeben.")
        return slug


class TenantUpdateForm(forms.Form):
    """Ändern der Stammdaten eines Mandanten (Kürzel bleibt unveränderlich)."""

    name = forms.CharField(label="Name", max_length=200, widget=forms.TextInput(attrs=_TEXT))
    gps_accuracy_threshold_m = forms.IntegerField(
        label="GPS-Genauigkeitsgrenze (Meter)",
        min_value=1,
        widget=forms.NumberInput(attrs=_NUMBER),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
