"""Views der Sensoren-App: Liste, Anlegen/Bearbeiten, Löschen und CSV-Import."""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import FormView, ListView

from apps.core.permissions import AdminRequiredMixin
from apps.sensors import services
from apps.sensors.forms import SensorCreateForm, SensorImportForm, SensorUpdateForm
from apps.sensors.models import Sensor


class SensorListView(AdminRequiredMixin, ListView[Sensor]):
    """Listet die Sensoren des Mandanten (mit Suche und Pagination)."""

    template_name = "sensors/sensor_list.html"
    context_object_name = "sensors"
    paginate_by = 25

    def get_queryset(self) -> Any:
        self.search = self.request.GET.get("q", "")
        return services.list_sensors(self.search)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["search"] = self.search
        return context


class SensorCreateView(AdminRequiredMixin, FormView[SensorCreateForm]):
    """Legt einen einzelnen Sensor an."""

    template_name = "sensors/sensor_form.html"
    form_class = SensorCreateForm
    success_url = reverse_lazy("sensors:list")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Sensor anlegen"
        return context

    def form_valid(self, form: SensorCreateForm) -> HttpResponse:
        services.create_sensor(
            dev_eui=form.cleaned_data["dev_eui"],
            manufacturer=form.cleaned_data["manufacturer"],
            sensor_type=form.cleaned_data["sensor_type"],
            serial_number=form.cleaned_data["serial_number"],
            note=form.cleaned_data["note"],
            actor=self.acting_user,
            request=self.request,
        )
        messages.success(self.request, "Sensor angelegt.")
        return super().form_valid(form)


class SensorUpdateView(AdminRequiredMixin, FormView[SensorUpdateForm]):
    """Bearbeitet die Stammdaten eines Sensors."""

    template_name = "sensors/sensor_form.html"
    form_class = SensorUpdateForm
    success_url = reverse_lazy("sensors:list")

    def get_object(self) -> Sensor:
        if not hasattr(self, "_object"):
            self._object = get_object_or_404(Sensor, pk=self.kwargs["pk"])
        return self._object

    def get_initial(self) -> dict[str, Any]:
        sensor = self.get_object()
        return {
            "manufacturer": sensor.manufacturer,
            "sensor_type": sensor.sensor_type,
            "serial_number": sensor.serial_number,
            "note": sensor.note,
        }

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Sensor bearbeiten"
        context["sensor"] = self.get_object()
        return context

    def form_valid(self, form: SensorUpdateForm) -> HttpResponse:
        services.update_sensor(
            self.get_object(),
            manufacturer=form.cleaned_data["manufacturer"],
            sensor_type=form.cleaned_data["sensor_type"],
            serial_number=form.cleaned_data["serial_number"],
            note=form.cleaned_data["note"],
            actor=self.acting_user,
            request=self.request,
        )
        messages.success(self.request, "Sensor aktualisiert.")
        return super().form_valid(form)


class SensorDeleteView(AdminRequiredMixin, View):
    """Löscht einen Sensor (nur per POST)."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponseRedirect:
        sensor = get_object_or_404(Sensor, pk=pk)
        services.delete_sensor(sensor, actor=self.acting_user, request=request)
        messages.success(request, "Sensor gelöscht.")
        return redirect("sensors:list")


class SensorImportView(AdminRequiredMixin, FormView[SensorImportForm]):
    """Importiert Sensoren aus einer hochgeladenen CSV-Datei und zeigt einen Bericht."""

    template_name = "sensors/sensor_import.html"
    form_class = SensorImportForm

    def form_valid(self, form: SensorImportForm) -> HttpResponse:
        upload = form.cleaned_data["file"]
        report = services.import_sensors_from_csv(
            data=upload.read(), actor=self.acting_user, request=self.request
        )
        # Bericht direkt anzeigen (kein Redirect), damit alle übersprungenen/fehlerhaften
        # Zeilen sichtbar bleiben.
        context = self.get_context_data(form=SensorImportForm(), report=report)
        if report.has_fatal_error:
            messages.error(self.request, report.fatal_error or "Import fehlgeschlagen.")
        else:
            messages.success(
                self.request,
                f"{report.created} Sensor(en) importiert, "
                f"{report.skipped_existing + report.skipped_duplicate} übersprungen, "
                f"{report.error_count} fehlerhaft.",
            )
        return self.render_to_response(context)
