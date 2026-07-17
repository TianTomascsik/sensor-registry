"""Views der Projekte-App: Liste, Detail, Anlegen/Bearbeiten und Zuweisungen.

Die Geschäftslogik liegt vollständig im Service-Layer (:mod:`apps.projects.services`).
Sichtbarkeit und Mandantentrennung werden dort bzw. über den ``TenantManager`` erzwungen.
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import FormView, ListView, TemplateView

from apps.accounts.models import User
from apps.core.permissions import AdminRequiredMixin, AuthenticatedViewMixin
from apps.projects import services
from apps.projects.forms import AssignUserForm, ProjectForm
from apps.projects.models import Project


class ProjectListView(AuthenticatedViewMixin, ListView[Project]):
    """Listet die für den Benutzer sichtbaren Projekte (mit Suche und Pagination)."""

    template_name = "projects/project_list.html"
    context_object_name = "projects"
    paginate_by = 25

    def get_queryset(self) -> Any:
        self.search = self.request.GET.get("q", "")
        return services.visible_projects(self.acting_user, self.search)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["search"] = self.search
        context["can_manage"] = self.acting_user.can_manage_users
        return context


class ProjectDetailView(AuthenticatedViewMixin, TemplateView):
    """Zeigt ein Projekt inkl. Zuweisungen; Administratoren können Zuweisungen ändern."""

    template_name = "projects/project_detail.html"

    def get_project(self) -> Project:
        if not hasattr(self, "_project"):
            try:
                self._project = services.get_visible_project(self.acting_user, self.kwargs["pk"])
            except Project.DoesNotExist as exc:
                raise Http404("Projekt nicht gefunden.") from exc
        return self._project

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        project = self.get_project()
        can_manage = self.acting_user.can_manage_users
        context["project"] = project
        context["assignments"] = services.assignments_for(project)
        context["can_manage"] = can_manage
        if can_manage:
            assigned_ids = [a.user_id for a in context["assignments"]]
            context["assign_form"] = AssignUserForm(
                users=services.assignable_users().exclude(pk__in=assigned_ids)
            )
        return context


class ProjectCreateView(AdminRequiredMixin, FormView[ProjectForm]):
    """Legt ein neues Projekt an."""

    template_name = "projects/project_form.html"
    form_class = ProjectForm
    success_url = reverse_lazy("projects:list")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Projekt anlegen"
        return context

    def form_valid(self, form: ProjectForm) -> HttpResponse:
        project = services.create_project(
            number=form.cleaned_data["number"],
            name=form.cleaned_data["name"],
            customer=form.cleaned_data["customer"],
            description=form.cleaned_data["description"],
            status=form.cleaned_data["status"],
            actor=self.acting_user,
            request=self.request,
        )
        messages.success(self.request, "Projekt angelegt.")
        return redirect("projects:detail", pk=project.pk)


class ProjectUpdateView(AdminRequiredMixin, FormView[ProjectForm]):
    """Bearbeitet ein Projekt."""

    template_name = "projects/project_form.html"
    form_class = ProjectForm

    def get_object(self) -> Project:
        if not hasattr(self, "_object"):
            self._object = get_object_or_404(Project, pk=self.kwargs["pk"])
        return self._object

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["exclude_pk"] = self.get_object().pk
        return kwargs

    def get_initial(self) -> dict[str, Any]:
        project = self.get_object()
        return {
            "number": project.number,
            "name": project.name,
            "customer": project.customer,
            "description": project.description,
            "status": project.status,
        }

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Projekt bearbeiten"
        context["project"] = self.get_object()
        return context

    def form_valid(self, form: ProjectForm) -> HttpResponse:
        project = services.update_project(
            self.get_object(),
            number=form.cleaned_data["number"],
            name=form.cleaned_data["name"],
            customer=form.cleaned_data["customer"],
            description=form.cleaned_data["description"],
            status=form.cleaned_data["status"],
            actor=self.acting_user,
            request=self.request,
        )
        messages.success(self.request, "Projekt aktualisiert.")
        return redirect("projects:detail", pk=project.pk)


class ProjectAssignView(AdminRequiredMixin, View):
    """Weist einem Projekt einen Benutzer zu (nur per POST)."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponseRedirect:
        project = get_object_or_404(Project, pk=pk)
        form = AssignUserForm(request.POST, users=services.assignable_users())
        if form.is_valid():
            services.assign_user(
                project, form.cleaned_data["user"], actor=self.acting_user, request=request
            )
            messages.success(request, "Benutzer zugewiesen.")
        else:
            messages.error(request, "Bitte einen gültigen Benutzer auswählen.")
        return redirect("projects:detail", pk=project.pk)


class ProjectUnassignView(AdminRequiredMixin, View):
    """Entfernt die Zuweisung eines Benutzers (nur per POST)."""

    def post(self, request: HttpRequest, pk: int, user_id: int) -> HttpResponseRedirect:
        project = get_object_or_404(Project, pk=pk)
        user = get_object_or_404(User, pk=user_id, tenant=project.tenant)
        services.unassign_user(project, user, actor=self.acting_user, request=request)
        messages.success(request, "Zuweisung entfernt.")
        return redirect("projects:detail", pk=project.pk)
