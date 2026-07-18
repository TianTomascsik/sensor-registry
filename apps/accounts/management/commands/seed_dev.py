"""Legt Standard-Entwicklungskonten an (idempotent).

Nur für die Entwicklung gedacht: erzeugt je einen Superadmin, Mandantenadministrator und
Monteur mit bekanntem Passwort, damit sich alle drei Rollen sofort ausprobieren lassen.
Wiederholte Aufrufe aktualisieren die vorhandenen Konten und setzen deren Passwort zurück –
es entstehen keine Dubletten.

Absichtlich fail-safe: Da hier schwache Passwörter gesetzt werden, verweigert der Befehl die
Ausführung außerhalb von ``DEBUG`` (Umgehung nur mit ``--force``).
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Role, User
from apps.core.models import Tenant
from apps.core.tenancy import tenant_context
from apps.projects.models import Project, ProjectAssignment, ProjectStatus
from apps.sensors.models import Sensor

#: Rollen-Konten, die angelegt werden. Der Superadmin besitzt bewusst keinen Mandanten.
_ACCOUNTS = [
    ("superadmin@dev.local", "Dev Superadmin", Role.SUPERADMIN, False),
    ("admin@dev.local", "Dev Mandantenadmin", Role.TENANT_ADMIN, True),
    ("monteur@dev.local", "Dev Monteur", Role.INSTALLER, True),
]

DEFAULT_PASSWORD = "dev12345"


class Command(BaseCommand):
    help = "Legt Standard-Entwicklungskonten (Superadmin, Mandantenadmin, Monteur) an."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--password",
            default=DEFAULT_PASSWORD,
            help=f"Passwort für alle Demokonten (Standard: {DEFAULT_PASSWORD}).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Ausführung auch außerhalb von DEBUG erlauben.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "seed_dev ist für die Entwicklung gedacht und vergibt schwache Passwörter. "
                "Außerhalb von DEBUG nur mit --force ausführen."
            )
        password: str = options["password"]

        tenant, tenant_created = Tenant.objects.get_or_create(
            slug="demo",
            defaults={"name": "Demo GmbH", "gps_accuracy_threshold_m": 5, "is_active": True},
        )
        self.stdout.write(
            f"Mandant: {tenant.name} ({'neu angelegt' if tenant_created else 'vorhanden'})"
        )

        users: dict[Role, User] = {}
        for email, full_name, role, needs_tenant in _ACCOUNTS:
            user = User.objects.filter(email=email).first() or User(email=email)
            user.full_name = full_name
            user.role = role
            user.tenant = tenant if needs_tenant else None
            user.is_active = True
            user.set_password(password)
            user.full_clean(exclude=["password"], validate_unique=False)
            user.save()
            users[role] = user
            self.stdout.write(f"  {role.label:22} {email}")

        # Projekt, Sensor und Zuweisung sind mandantengebunden → im Mandantenkontext anlegen.
        # Der Monteur wird dem Projekt zugewiesen, sonst sähe er es in der Erfassung nicht
        # (Monteure sehen ausschließlich ihnen zugewiesene Projekte).
        with tenant_context(tenant):
            project, _ = Project.objects.get_or_create(
                number="DEMO-1",
                defaults={
                    "name": "Demo-Projekt",
                    "customer": "Demo-Kunde",
                    "status": ProjectStatus.ACTIVE,
                },
            )
            sensor, _ = Sensor.objects.get_or_create(
                dev_eui="70B3D57ED0012345",
                defaults={"manufacturer": "Demo", "sensor_type": "Bodenfeuchte"},
            )
            ProjectAssignment.objects.get_or_create(project=project, user=users[Role.INSTALLER])
        self.stdout.write(
            f"  Projekt {project.number} · Sensor {sensor.dev_eui} (Monteur zugewiesen)"
        )

        self.stdout.write(
            self.style.SUCCESS(f"Demokonten bereit. Passwort für alle: {password}")
        )
