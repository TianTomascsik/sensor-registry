"""Projektmodelle.

``Project`` und ``ProjectAssignment`` sind die ersten produktiven mandantengebundenen
Fachmodelle. Sie erben von :class:`apps.core.tenancy.TenantModel` und werden dadurch
automatisch auf den aktiven Mandanten eingeschränkt (fail-closed).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.tenancy import TenantModel


class ProjectStatus(models.TextChoices):
    """Lebenszyklus eines Projekts (kompaktes Modell, später erweiterbar)."""

    ACTIVE = "active", "Aktiv"
    COMPLETED = "completed", "Abgeschlossen"
    ARCHIVED = "archived", "Archiviert"


class Project(TenantModel):
    """Ein Projekt eines Mandanten.

    Die Projektnummer ist innerhalb eines Mandanten eindeutig. Benutzer sehen nur die
    ihnen zugewiesenen Projekte (Monteure) bzw. alle Projekte des Mandanten (Admins).
    """

    number = models.CharField("Projektnummer", max_length=50)
    name = models.CharField("Name", max_length=200)
    customer = models.CharField("Kunde", max_length=200, blank=True)
    description = models.TextField("Beschreibung", blank=True)
    status = models.CharField(
        "Status",
        max_length=20,
        choices=ProjectStatus.choices,
        default=ProjectStatus.ACTIVE,
    )
    created_at = models.DateTimeField("Erstellt am", default=timezone.now, editable=False)

    class Meta:
        verbose_name = "Projekt"
        verbose_name_plural = "Projekte"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "number"],
                name="project_number_unique_per_tenant",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.number} – {self.name}"


class ProjectAssignment(TenantModel):
    """Zuweisung eines Benutzers zu einem Projekt.

    Explizites Zwischenmodell (statt automatischer M2M-Tabelle), damit auch die Zuweisung
    mandantengebunden ist und der Zeitpunkt/Urheber protokollierbar bleibt.
    """

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="assignments",
        verbose_name="Projekt",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="project_assignments",
        verbose_name="Benutzer",
    )
    assigned_at = models.DateTimeField("Zugewiesen am", default=timezone.now, editable=False)

    class Meta:
        verbose_name = "Projektzuweisung"
        verbose_name_plural = "Projektzuweisungen"
        ordering = ["project", "user"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "user"],
                name="assignment_unique_project_user",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} → {self.project}"
