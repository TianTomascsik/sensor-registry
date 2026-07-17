"""Mandantenkontext und -durchsetzung (fail-closed).

Dieses Modul ist das Herzstück der Mandantentrennung. Es hält pro Request (bzw. pro
Ausführungskontext) fest, welcher Mandant gerade "aktiv" ist, und stellt eine
Model-Basisklasse bereit, deren Standard-Manager Abfragen automatisch auf diesen
Mandanten einschränkt.

Zentrale Sicherheitsgarantie – *fail closed*:
    Ist kein Kontext gesetzt, liefert der Manager **keine** Daten, sondern wirft
    :class:`TenantContextMissing`. Ein vergessener Kontext führt damit zu einem harten,
    sofort sichtbaren Fehler – niemals stillschweigend zur Preisgabe aller Mandanten.

Drei mögliche Zustände des Kontexts:
    * ``UNSET``  – kein Kontext etabliert  → Zugriff wirft ``TenantContextMissing``.
    * eine ``Tenant``-Instanz              → Abfragen werden auf diesen Mandanten gefiltert.
    * ``SYSTEM`` – bewusster Vollzugriff   → Abfragen bleiben ungefiltert (nur Superadmin
      bzw. Wartungspfade dürfen diesen Zustand über :func:`system_context` betreten).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Any, Final, TypeVar

from django.db import models

if TYPE_CHECKING:
    from apps.core.models import Tenant

#: Typvariable für den konkreten mandantengebundenen Modelltyp, damit Manager und QuerySet
#: den jeweiligen Modelltyp (z. B. Sensor, Project) statt der abstrakten Basis liefern.
_M = TypeVar("_M", bound=models.Model)


class _Sentinel:
    """Eindeutiger, gut lesbarer Marker für Sonderzustände des Kontexts."""

    __slots__ = ("_name",)

    def __init__(self, name: str) -> None:
        self._name = name

    def __repr__(self) -> str:  # pragma: no cover - reine Diagnoseausgabe
        return f"<{self._name}>"


# Kein Kontext gesetzt (fail-closed) bzw. bewusster mandantenübergreifender Vollzugriff.
UNSET: Final = _Sentinel("TENANT_UNSET")
SYSTEM: Final = _Sentinel("TENANT_SYSTEM")

# Der eigentliche, ausführungslokale Kontextspeicher. Standard ist UNSET (fail-closed).
_current: ContextVar[Any] = ContextVar("papa_tenant", default=UNSET)


class TenantContextMissing(RuntimeError):
    """Wird geworfen, wenn ohne etablierten Mandantenkontext auf Mandantendaten
    zugegriffen wird. Signalisiert einen Programmierfehler, keinen Benutzerfehler."""


class TenantScopeViolation(RuntimeError):
    """Wird geworfen, wenn ein Objekt eines anderen als des aktiven Mandanten
    geschrieben werden soll – ein Schutz gegen versehentliche Cross-Tenant-Writes."""


def get_state() -> Any:
    """Gibt den rohen Kontextzustand zurück (``UNSET``, ``SYSTEM`` oder eine ``Tenant``)."""
    return _current.get()


def current_tenant() -> Tenant:
    """Gibt den aktiven Mandanten zurück.

    :raises TenantContextMissing: wenn kein Mandantenkontext gesetzt ist oder der
        System-(Vollzugriffs-)Kontext aktiv ist, in dem es keinen eindeutigen Mandanten
        gibt. Aufrufer, die auch den Systemkontext akzeptieren, nutzen
        :func:`current_tenant_or_none`.
    """
    state = _current.get()
    if isinstance(state, _Sentinel):
        raise TenantContextMissing(
            "Kein eindeutiger Mandantenkontext aktiv. Code, der einen konkreten "
            "Mandanten benötigt, muss innerhalb von tenant_context(...) laufen."
        )
    return state


def current_tenant_or_none() -> Tenant | None:
    """Wie :func:`current_tenant`, gibt im Systemkontext jedoch ``None`` zurück.

    :raises TenantContextMissing: nur, wenn überhaupt kein Kontext gesetzt ist.
    """
    state = _current.get()
    if state is UNSET:
        raise TenantContextMissing("Kein Mandantenkontext aktiv.")
    if state is SYSTEM:
        return None
    return state


def is_system_context() -> bool:
    """True, wenn der bewusste mandantenübergreifende Vollzugriff aktiv ist."""
    return _current.get() is SYSTEM


@contextmanager
def tenant_context(tenant: Tenant) -> Iterator[Tenant]:
    """Etabliert den Mandantenkontext für die Dauer des ``with``-Blocks.

    Der vorherige Zustand wird beim Verlassen zuverlässig wiederhergestellt – auch im
    Fehlerfall –, sodass sich Kontexte sauber verschachteln lassen.
    """
    if tenant is None:  # defensive Prüfung: None ist dem Systemkontext vorbehalten
        raise ValueError("tenant_context erfordert eine Tenant-Instanz, nicht None.")
    token: Token[Any] = _current.set(tenant)
    try:
        yield tenant
    finally:
        _current.reset(token)


@contextmanager
def system_context() -> Iterator[None]:
    """Etabliert den bewussten mandantenübergreifenden Vollzugriff (Superadmin/Wartung).

    Ausschließlich für explizit autorisierte Pfade (Superadmin-Ansichten,
    Management-Befehle, Migrationen). Innerhalb bleiben Mandanten-Querysets ungefiltert.
    """
    token: Token[Any] = _current.set(SYSTEM)
    try:
        yield None
    finally:
        _current.reset(token)


class TenantQuerySet(models.QuerySet[_M]):
    """QuerySet für mandantengebundene Modelle.

    Enthält keine Sonderlogik – die Filterung erfolgt zentral im Manager, damit sie sich
    nicht durch das Anhängen weiterer QuerySet-Methoden umgehen lässt.
    """


class TenantManager(models.Manager[_M]):
    """Standard-Manager mandantengebundener Modelle.

    Schränkt jede Abfrage automatisch auf den aktiven Mandanten ein. Ohne Kontext wird
    hart abgebrochen (fail-closed); im Systemkontext bleibt die Abfrage ungefiltert.
    """

    def get_queryset(self) -> TenantQuerySet[_M]:
        state = _current.get()
        if state is UNSET:
            raise TenantContextMissing(
                f"Zugriff auf {self.model.__name__} ohne aktiven Mandantenkontext. "
                "Fehlt eine umschließende tenant_context(...)/system_context()-Klammer "
                "oder die TenantContextMiddleware?"
            )
        qs: TenantQuerySet[_M] = TenantQuerySet(self.model, using=self._db)
        if state is SYSTEM:
            return qs
        return qs.filter(tenant=state)


class TenantModel(models.Model):
    """Abstrakte Basisklasse für alle mandantengebundenen Fachmodelle.

    * ``objects``   – mandantengefilterter Standard-Manager (fail-closed).
    * ``unscoped``  – ungefilterter Manager für Djangos interne Operationen
      (FK-Validierung, ``refresh_from_db``, Kaskaden-Sammlung beim Löschen) sowie für
      explizit autorisierte Wartungszugriffe.

    ``Meta.base_manager_name = "unscoped"`` ist essenziell: Andernfalls würde Django seine
    internen Abfragen über den gefilterten Manager ausführen und Kaskaden/FK-Prüfungen im
    Superadmin- bzw. Systemkontext bräche zusammen.
    """

    tenant = models.ForeignKey(
        "core.Tenant",
        on_delete=models.CASCADE,
        related_name="%(class)ss",
        editable=False,
        verbose_name="Mandant",
    )
    if TYPE_CHECKING:
        # Django erzeugt das ``*_id``-Attribut zur Laufzeit; für den Typechecker deklariert.
        tenant_id: int | None

    objects = TenantManager()
    unscoped = models.Manager()

    class Meta:
        abstract = True
        base_manager_name = "unscoped"
        default_manager_name = "objects"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Setzt den Mandanten aus dem Kontext bzw. verhindert Cross-Tenant-Writes.

        * Ist noch kein Mandant gesetzt, wird der aktive Kontext-Mandant übernommen.
        * Ist bereits ein Mandant gesetzt, muss er (im Mandantenkontext) mit dem aktiven
          übereinstimmen – sonst :class:`TenantScopeViolation`.
        """
        state = _current.get()
        if self.tenant_id is None:
            if isinstance(state, _Sentinel):
                raise TenantContextMissing(
                    f"{type(self).__name__} kann ohne aktiven Mandantenkontext nicht "
                    "gespeichert werden (kein Mandant zum Zuordnen)."
                )
            self.tenant = state
        elif not isinstance(state, _Sentinel) and self.tenant_id != state.pk:
            raise TenantScopeViolation(
                f"{type(self).__name__} gehört zu Mandant {self.tenant_id}, "
                f"der aktive Kontext ist Mandant {state.pk}."
            )
        super().save(*args, **kwargs)
