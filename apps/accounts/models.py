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
