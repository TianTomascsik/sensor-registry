"""Benutzermodell und Rollen.

Der Benutzer ist bewusst **nicht** mandantengebunden im Sinne von
:class:`apps.core.tenancy.TenantModel`: Superadmins besitzen keinen Mandanten
(``tenant = None``) und Benutzer werden während der Authentifizierung abgefragt, bevor
ein Mandantenkontext existiert. Die Mandantenzuordnung erfolgt über das nullbare Feld
``tenant``; Abfragen im Benutzer-Management filtern explizit über den Service-Layer.
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.db import models
from django.utils import timezone


class Role(models.TextChoices):
    """Die drei Systemrollen."""

    SUPERADMIN = "superadmin", "Superadmin"
    TENANT_ADMIN = "tenant_admin", "Mandantenadministrator"
    INSTALLER = "installer", "Monteur"


class UserManager(BaseUserManager["User"]):
    """Manager mit E-Mail-basierter Benutzererzeugung."""

    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra: object) -> User:
        if not email:
            raise ValueError("Eine E-Mail-Adresse ist erforderlich.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.full_clean(exclude=["password"], validate_unique=False)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra: object) -> User:
        """Erzeugt einen regulären Benutzer (Standardrolle: Monteur)."""
        extra.setdefault("role", Role.INSTALLER)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str, **extra: object) -> User:
        """Erzeugt einen Superadmin (für ``manage.py createsuperuser``)."""
        extra["role"] = Role.SUPERADMIN
        extra["tenant"] = None
        extra.setdefault("is_active", True)
        return self._create_user(email, password, **extra)


class User(AbstractBaseUser):
    """Anwendungsbenutzer. Anmeldung erfolgt über die E-Mail-Adresse."""

    #: Von der Mandantenprüfung ausgenommen (siehe Modul-Docstring).
    tenant_exempt = True

    email = models.EmailField("E-Mail", unique=True)
    full_name = models.CharField("Vollständiger Name", max_length=200)
    role = models.CharField("Rolle", max_length=20, choices=Role.choices)
    tenant = models.ForeignKey(
        "core.Tenant",
        on_delete=models.CASCADE,
        related_name="users",
        null=True,
        blank=True,
        verbose_name="Mandant",
        help_text="Für Superadmins leer; für alle anderen Rollen zwingend.",
    )
    is_active = models.BooleanField("Aktiv", default=True)
    date_joined = models.DateTimeField("Angelegt am", default=timezone.now, editable=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        verbose_name = "Benutzer"
        verbose_name_plural = "Benutzer"
        ordering = ["full_name"]
        constraints = [
            # Superadmins haben keinen Mandanten, alle anderen Rollen zwingend einen.
            models.CheckConstraint(
                condition=(
                    models.Q(role="superadmin", tenant__isnull=True)
                    | (~models.Q(role="superadmin") & models.Q(tenant__isnull=False))
                ),
                name="user_tenant_matches_role",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} <{self.email}>"

    @property
    def is_superadmin(self) -> bool:
        return self.role == Role.SUPERADMIN

    @property
    def is_tenant_admin(self) -> bool:
        return self.role == Role.TENANT_ADMIN

    @property
    def is_installer(self) -> bool:
        return self.role == Role.INSTALLER

    @property
    def can_manage_users(self) -> bool:
        """Superadmins und Mandantenadmins dürfen Benutzer verwalten."""
        return self.role in (Role.SUPERADMIN, Role.TENANT_ADMIN)


class DeviceInvite(models.Model):
    """Einmalige, ablaufende Einladung zur Registrierung eines Monteur-Geräts.

    Der Klartext-Token wird nur im Einladungslink/QR-Code ausgeliefert; in der Datenbank
    liegt ausschließlich sein SHA-256-Hash. Die Einlösung erfolgt atomar (bedingtes UPDATE
    auf ``used_at``), sodass eine Einladung nicht doppelt verwendet werden kann.

    Von der Mandantenprüfung ausgenommen: Der Registrierungs-Flow ruft die Einladung anhand
    des Token-Hashes ab, bevor ein Mandantenkontext existiert.
    """

    tenant_exempt = True

    tenant = models.ForeignKey(
        "core.Tenant",
        on_delete=models.CASCADE,
        related_name="device_invites",
        verbose_name="Mandant",
    )
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="device_invites",
        verbose_name="Monteur",
    )
    token_hash = models.CharField("Token-Hash", max_length=64, unique=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_device_invites",
        verbose_name="Erstellt von",
    )
    created_at = models.DateTimeField("Erstellt am", default=timezone.now, editable=False)
    expires_at = models.DateTimeField("Gültig bis")
    used_at = models.DateTimeField("Eingelöst am", null=True, blank=True)

    class Meta:
        verbose_name = "Geräteeinladung"
        verbose_name_plural = "Geräteeinladungen"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Einladung für {self.user.full_name}"

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_valid(self) -> bool:
        return not self.is_used and not self.is_expired


class Device(models.Model):
    """Ein registriertes Monteur-Gerät mit dauerhaftem Zugangstoken.

    In der Datenbank liegt nur der SHA-256-Hash des Gerätetokens; der Klartext-Token wird
    einmalig als HttpOnly-Cookie im Browser des Geräts gespeichert. Ein gesperrtes Gerät
    (``revoked_at`` gesetzt) verliert beim nächsten Request sofort den Zugriff.

    Von der Mandantenprüfung ausgenommen: Die Authentifizierung ruft das Gerät anhand des
    Token-Hashes ab, bevor ein Mandantenkontext existiert.
    """

    tenant_exempt = True

    tenant = models.ForeignKey(
        "core.Tenant",
        on_delete=models.CASCADE,
        related_name="devices",
        verbose_name="Mandant",
    )
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="devices",
        verbose_name="Monteur",
    )
    label = models.CharField("Bezeichnung", max_length=150, blank=True)
    token_hash = models.CharField("Token-Hash", max_length=64, unique=True)
    user_agent = models.CharField("User-Agent", max_length=400, blank=True)
    created_at = models.DateTimeField("Registriert am", default=timezone.now, editable=False)
    last_seen = models.DateTimeField("Zuletzt gesehen", null=True, blank=True)
    revoked_at = models.DateTimeField("Gesperrt am", null=True, blank=True)

    class Meta:
        verbose_name = "Gerät"
        verbose_name_plural = "Geräte"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "-created_at"]),
        ]

    def __str__(self) -> str:
        return self.label or f"Gerät {self.pk}"

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None
