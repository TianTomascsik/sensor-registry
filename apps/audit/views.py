"""Audit-Log-Ansicht (nur Superadmin, filterbar).

Respektiert den Mandanten-Umschalter: Ist ein Mandant gewählt, werden nur dessen Einträge
gezeigt, sonst alle (Gesamtsicht).
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any

from django.utils import timezone
from django.views.generic import ListView

from apps.audit.forms import AuditFilterForm
from apps.audit.models import AuditLog
from apps.core.permissions import SuperadminRequiredMixin
from apps.core.tenancy import current_tenant_or_none


class AuditLogListView(SuperadminRequiredMixin, ListView[AuditLog]):
    """Listet Audit-Einträge mit Filtern und Pagination."""

    template_name = "audit/audit_list.html"
    context_object_name = "entries"
    paginate_by = 50

    def get_form(self) -> AuditFilterForm:
        if not hasattr(self, "_form"):
            self._form = AuditFilterForm(self.request.GET or None)
        return self._form

    def get_queryset(self) -> Any:
        scope = current_tenant_or_none()
        qs = AuditLog.objects.select_related("actor", "tenant")
        if scope is not None:
            qs = qs.filter(tenant=scope)

        form = self.get_form()
        if form.is_valid():
            data = form.cleaned_data
            if data.get("action"):
                qs = qs.filter(action=data["action"])
            if data.get("actor"):
                qs = qs.filter(actor__email__icontains=data["actor"])
            if data.get("q"):
                qs = qs.filter(object_repr__icontains=data["q"])
            if data.get("date_from"):
                start = timezone.make_aware(datetime.combine(data["date_from"], time.min))
                qs = qs.filter(created_at__gte=start)
            if data.get("date_to"):
                end = timezone.make_aware(datetime.combine(data["date_to"], time.max))
                qs = qs.filter(created_at__lte=end)
        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["form"] = self.get_form()
        return context
