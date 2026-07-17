"""Formulare der Projekte-App."""

from __future__ import annotations

from typing import Any, cast

from django import forms
from django.db.models import QuerySet

from apps.accounts.models import User
from apps.projects.models import Project, ProjectStatus

_TEXT = {"class": "form-control form-control-lg"}
_SELECT = {"class": "form-select form-select-lg"}
_AREA = {"class": "form-control form-control-lg", "rows": 3}


class ProjectForm(forms.Form):
    """Anlegen und Bearbeiten eines Projekts.

    Die Projektnummer muss innerhalb des Mandanten eindeutig sein. Da die Formulare stets
    im Mandantenkontext instanziiert werden, prüft ``clean_number`` gegen den mandanten-
    gefilterten Manager.
    """

    number = forms.CharField(
        label="Projektnummer", max_length=50, widget=forms.TextInput(attrs=_TEXT)
    )
    name = forms.CharField(label="Name", max_length=200, widget=forms.TextInput(attrs=_TEXT))
    customer = forms.CharField(
        label="Kunde", max_length=200, required=False, widget=forms.TextInput(attrs=_TEXT)
    )
    description = forms.CharField(
        label="Beschreibung", required=False, widget=forms.Textarea(attrs=_AREA)
    )
    status = forms.ChoiceField(
        label="Status", choices=ProjectStatus.choices, widget=forms.Select(attrs=_SELECT)
    )

    def __init__(self, *args: Any, exclude_pk: int | None = None, **kwargs: Any) -> None:
        self._exclude_pk = exclude_pk
        super().__init__(*args, **kwargs)

    def clean_number(self) -> str:
        number = self.cleaned_data["number"].strip()
        qs = Project.objects.filter(number=number)
        if self._exclude_pk is not None:
            qs = qs.exclude(pk=self._exclude_pk)
        if qs.exists():
            raise forms.ValidationError("Diese Projektnummer ist bereits vergeben.")
        return number


class AssignUserForm(forms.Form):
    """Auswahl eines Benutzers zur Zuweisung an ein Projekt."""

    user = forms.ModelChoiceField(
        label="Benutzer",
        queryset=User.objects.none(),
        widget=forms.Select(attrs=_SELECT),
        empty_label="Benutzer auswählen …",
    )

    def __init__(self, *args: Any, users: QuerySet[User], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        cast("forms.ModelChoiceField[User]", self.fields["user"]).queryset = users
