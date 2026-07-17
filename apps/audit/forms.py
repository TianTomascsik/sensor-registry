"""Formular zur Filterung des Audit-Logs."""

from __future__ import annotations

from django import forms

from apps.audit.models import AuditAction


class AuditFilterForm(forms.Form):
    """Filter für die Audit-Log-Ansicht (alle Felder optional)."""

    action = forms.ChoiceField(
        label="Aktion",
        required=False,
        choices=[("", "Alle Aktionen"), *AuditAction.choices],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    actor = forms.CharField(
        label="Benutzer (E-Mail)",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "E-Mail-Teil"}),
    )
    q = forms.CharField(
        label="Objekt",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Objektbezeichnung"}),
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
