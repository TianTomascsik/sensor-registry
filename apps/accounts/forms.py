"""Formulare der Accounts-App: Anmeldung und Benutzerverwaltung."""

from __future__ import annotations

from typing import Any, cast

from django import forms

from apps.accounts.models import Role, User

_TEXT = {"class": "form-control form-control-lg"}
_SELECT = {"class": "form-select form-select-lg"}


def _set_role_choices(form: forms.Form, choices: list[tuple[str, str]]) -> None:
    """Setzt die Auswahlwerte des ``role``-Feldes (typsicher)."""
    cast(forms.ChoiceField, form.fields["role"]).choices = choices


class LoginForm(forms.Form):
    """Anmeldung per E-Mail-Adresse und Passwort."""

    email = forms.EmailField(
        label="E-Mail",
        widget=forms.EmailInput(attrs={**_TEXT, "autocomplete": "email", "autofocus": True}),
    )
    password = forms.CharField(
        label="Passwort",
        widget=forms.PasswordInput(attrs={**_TEXT, "autocomplete": "current-password"}),
    )


class UserCreateForm(forms.Form):
    """Anlegen eines Benutzers innerhalb eines Mandanten.

    Für Mandantenadministratoren ist ein Passwort verpflichtend. Monteure können ohne
    Passwort angelegt werden; ihr Zugang erfolgt später über die Geräteanmeldung.
    """

    full_name = forms.CharField(
        label="Vollständiger Name", max_length=200, widget=forms.TextInput(attrs=_TEXT)
    )
    email = forms.EmailField(label="E-Mail", widget=forms.EmailInput(attrs=_TEXT))
    role = forms.ChoiceField(label="Rolle", widget=forms.Select(attrs=_SELECT))
    password = forms.CharField(
        label="Passwort",
        required=False,
        widget=forms.PasswordInput(attrs={**_TEXT, "autocomplete": "new-password"}),
        help_text="Für Mandantenadministratoren erforderlich; für Monteure optional.",
    )

    def __init__(self, *args: Any, role_choices: list[tuple[str, str]], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _set_role_choices(self, role_choices)

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Diese E-Mail-Adresse wird bereits verwendet.")
        return email

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        role = cleaned.get("role")
        password = cleaned.get("password")
        if role == Role.TENANT_ADMIN and not password:
            self.add_error(
                "password", "Für Mandantenadministratoren ist ein Passwort erforderlich."
            )
        return cleaned


class UserUpdateForm(forms.Form):
    """Ändern von Name und Rolle eines bestehenden Benutzers."""

    full_name = forms.CharField(
        label="Vollständiger Name", max_length=200, widget=forms.TextInput(attrs=_TEXT)
    )
    role = forms.ChoiceField(label="Rolle", widget=forms.Select(attrs=_SELECT))

    def __init__(self, *args: Any, role_choices: list[tuple[str, str]], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _set_role_choices(self, role_choices)
