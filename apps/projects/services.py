"""Service-Layer der Projekte-App: Verwaltung, Sichtbarkeit und Zuweisungen.

Sichtbarkeit: Administratoren (Superadmin, Mandantenadministrator) sehen alle Projekte
ihres Mandanten; Monteure sehen ausschließlich die ihnen zugewiesenen Projekte. Die
Mandantentrennung selbst erfolgt bereits automatisch über den ``TenantManager``.
"""

from __future__ import annotations

from django.db.models import Q, QuerySet
from django.http import HttpRequest

from apps.accounts.models import Role, User
from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.core.tenancy import current_tenant
from apps.projects.models import Project, ProjectAssignment


def visible_projects(user: User, search: str = "") -> QuerySet[Project]:
    """Für den Benutzer sichtbare Projekte des aktiven Mandanten, optional gefiltert."""
    qs = Project.objects.all()
    if user.role == Role.INSTALLER:
        qs = qs.filter(assignments__user=user)
    term = search.strip()
    if term:
        qs = qs.filter(
            Q(number__icontains=term)
            | Q(name__icontains=term)
            | Q(customer__icontains=term)
            | Q(description__icontains=term)
        )
    return qs.distinct()


def get_visible_project(user: User, pk: int) -> Project:
    """Lädt ein für den Benutzer sichtbares Projekt (sonst ``Project.DoesNotExist``)."""
    return visible_projects(user).get(pk=pk)


def create_project(
    *,
    number: str,
    name: str,
    customer: str,
    description: str,
    status: str,
    actor: User,
    request: HttpRequest | None = None,
) -> Project:
    """Legt ein Projekt an und protokolliert die Aktion."""
    project = Project.objects.create(
        number=number,
        name=name,
        customer=customer,
        description=description,
        status=status,
    )
    record(
        AuditAction.PROJECT_CREATED,
        actor=actor,
        obj=project,
        changes={"number": number, "name": name, "status": status},
        request=request,
    )
    return project


def update_project(
    project: Project,
    *,
    number: str,
    name: str,
    customer: str,
    description: str,
    status: str,
    actor: User,
    request: HttpRequest | None = None,
) -> Project:
    """Aktualisiert ein Projekt und protokolliert die geänderten Felder."""
    changes: dict[str, dict[str, str]] = {}
    for field_name, new in (
        ("number", number),
        ("name", name),
        ("customer", customer),
        ("description", description),
        ("status", status),
    ):
        old = getattr(project, field_name)
        if old != new:
            changes[field_name] = {"von": str(old), "zu": str(new)}
            setattr(project, field_name, new)
    if changes:
        project.save(update_fields=list(changes.keys()))
        record(
            AuditAction.PROJECT_UPDATED,
            actor=actor,
            obj=project,
            changes=changes,
            request=request,
        )
    return project


def assignable_users() -> QuerySet[User]:
    """Aktive Benutzer des aktiven Mandanten, die einem Projekt zugewiesen werden können."""
    return User.objects.filter(
        tenant=current_tenant(),
        is_active=True,
        role__in=[Role.TENANT_ADMIN, Role.INSTALLER],
    ).order_by("full_name")


def assignments_for(project: Project) -> QuerySet[ProjectAssignment]:
    """Zuweisungen eines Projekts (inkl. Benutzerdaten)."""
    return project.assignments.select_related("user").order_by("user__full_name")


def assign_user(
    project: Project,
    user: User,
    *,
    actor: User,
    request: HttpRequest | None = None,
) -> ProjectAssignment:
    """Weist einem Projekt einen Benutzer zu (idempotent)."""
    assignment, created = ProjectAssignment.objects.get_or_create(project=project, user=user)
    if created:
        record(
            AuditAction.PROJECT_ASSIGNED,
            actor=actor,
            obj=project,
            changes={"benutzer": user.email},
            request=request,
        )
    return assignment


def unassign_user(
    project: Project,
    user: User,
    *,
    actor: User,
    request: HttpRequest | None = None,
) -> None:
    """Entfernt die Zuweisung eines Benutzers zu einem Projekt."""
    deleted, _ = ProjectAssignment.objects.filter(project=project, user=user).delete()
    if deleted:
        record(
            AuditAction.PROJECT_UNASSIGNED,
            actor=actor,
            obj=project,
            changes={"benutzer": user.email},
            request=request,
        )
