"""Formulare der Installationen-App (administrative Korrektur und Storno)."""

from __future__ import annotations

from typing import Any, cast

from django import forms
from django.db.models import QuerySet

from apps.accounts.models import User
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


class InstallationSearchForm(forms.Form):
    """Globale Suche über Installationen (mehrere Kriterien, alle optional)."""

    q = forms.CharField(
        label="Suchbegriff",
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "DevEUI, Projekt, Beschreibung …"}
        ),
    )
    project = forms.ModelChoiceField(
        label="Projekt",
        required=False,
        queryset=Project.unscoped.none(),
        empty_label="Alle Projekte",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    deveui = forms.CharField(
        label="DevEUI",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "DevEUI"}),
    )
    installer = forms.ModelChoiceField(
        label="Benutzer",
        required=False,
        queryset=User.objects.none(),
        empty_label="Alle Benutzer",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    date_from = forms.DateField(
        label="Von",
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    date_to = forms.DateField(
        label="Bis",
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )

    def __init__(
        self,
        *args: Any,
        projects: QuerySet[Project],
        installers: QuerySet[User],
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        cast("forms.ModelChoiceField[Project]", self.fields["project"]).queryset = projects
        cast("forms.ModelChoiceField[User]", self.fields["installer"]).queryset = installers
