"""Audit-Log: revisionssicheres Protokoll sicherheits- und datenrelevanter Ereignisse.

Der Eintrag ist **nicht** mandantengebunden im Sinne von ``TenantModel``: Er wird auch für
mandantenlose Ereignisse geschrieben (fehlgeschlagene Anmeldung ohne bekannten Benutzer,
Superadmin-Aktionen). Das Feld ``tenant`` ist daher nullbar; die Audit-Ansicht filtert
explizit.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class AuditAction(models.TextChoices):
    """Katalog protokollierter Aktionen. Erweiterbar in späteren Phasen."""

    LOGIN = "login", "Anmeldung"
    LOGIN_FAILED = "login_failed", "Fehlgeschlagene Anmeldung"
    LOGOUT = "logout", "Abmeldung"
    TENANT_CREATED = "tenant_created", "Mandant angelegt"
    TENANT_UPDATED = "tenant_updated", "Mandant geändert"
    TENANT_DEACTIVATED = "tenant_deactivated", "Mandant deaktiviert"
    TENANT_ACTIVATED = "tenant_activated", "Mandant aktiviert"
    USER_CREATED = "user_created", "Benutzer angelegt"
    USER_UPDATED = "user_updated", "Benutzer geändert"
    USER_DEACTIVATED = "user_deactivated", "Benutzer deaktiviert"
    USER_ACTIVATED = "user_activated", "Benutzer aktiviert"
    PROJECT_CREATED = "project_created", "Projekt angelegt"
    PROJECT_UPDATED = "project_updated", "Projekt geändert"
    PROJECT_ASSIGNED = "project_assigned", "Projekt zugewiesen"
    PROJECT_UNASSIGNED = "project_unassigned", "Projektzuweisung entfernt"
    SENSOR_CREATED = "sensor_created", "Sensor angelegt"
    SENSOR_UPDATED = "sensor_updated", "Sensor geändert"
    SENSOR_DELETED = "sensor_deleted", "Sensor gelöscht"
    SENSOR_IMPORTED = "sensor_imported", "Sensoren importiert"
    DEVICE_INVITE_CREATED = "device_invite_created", "Geräteeinladung erstellt"
    DEVICE_INVITE_REVOKED = "device_invite_revoked", "Geräteeinladung widerrufen"
    DEVICE_REGISTERED = "device_registered", "Gerät registriert"
    DEVICE_REVOKED = "device_revoked", "Gerät gesperrt"
    DEVICE_REMOVED = "device_removed", "Gerät entfernt"


class AuditLog(models.Model):
    """Ein einzelnes, unveränderliches Protokollereignis."""

    #: Von der Mandantenprüfung ausgenommen (siehe Modul-Docstring).
    tenant_exempt = True

    created_at = models.DateTimeField("Zeitpunkt", default=timezone.now, editable=False)
    tenant = models.ForeignKey(
        "core.Tenant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        verbose_name="Mandant",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        verbose_name="Benutzer",
    )
    action = models.CharField("Aktion", max_length=40, choices=AuditAction.choices)
    object_type = models.CharField("Objekttyp", max_length=100, blank=True)
    object_id = models.CharField("Objekt-ID", max_length=64, blank=True)
    object_repr = models.CharField("Objektbezeichnung", max_length=255, blank=True)
    changes = models.JSONField("Änderungen", default=dict, blank=True)
    ip_address = models.GenericIPAddressField("IP-Adresse", null=True, blank=True)
    user_agent = models.CharField("User-Agent", max_length=400, blank=True)

    class Meta:
        verbose_name = "Audit-Eintrag"
        verbose_name_plural = "Audit-Log"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["tenant", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.get_action_display()}"
