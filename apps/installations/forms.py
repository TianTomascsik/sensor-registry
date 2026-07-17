"""Formulare der Installationen-App (administrative Korrektur und Storno)."""

from __future__ import annotations

from typing import Any, cast

from django import forms
from django.db.models import QuerySet

from apps.projects.models import Project

_SELECT = {"class": "form-select form-select-lg"}
_AREA = {"class": "form-control form-control-lg", "rows": 3}


class InstallationCorrectForm(forms.Form):
    """Korrektur der Projektzuordnung und Beschreibung einer Installation."""

    project = forms.ModelChoiceField(
        label="Projekt",
        # Leerer Platzhalter über den ungefilterten Manager (kein Mandantenkontext beim
        # Import); die tatsächliche Auswahl wird in __init__ gesetzt.
        queryset=Project.unscoped.none(),
        widget=forms.Select(attrs=_SELECT),
    )
    description = forms.CharField(
        label="Beschreibung", required=False, widget=forms.Textarea(attrs=_AREA)
    )

    def __init__(self, *args: Any, projects: QuerySet[Project], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        cast("forms.ModelChoiceField[Project]", self.fields["project"]).queryset = projects


class InstallationCancelForm(forms.Form):
    """Storno einer Installation mit Begründung."""

    reason = forms.CharField(
        label="Stornogrund",
        widget=forms.Textarea(attrs={**_AREA, "placeholder": "z. B. falscher Sensor erfasst"}),
    )
