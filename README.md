# Sensor-Dokumentation

Mandantenfähige Webanwendung zur Dokumentation von LoRaWAN-Bodensensor-Installationen:
Sie hält fest, **wo, wann, durch welchen Monteur und in welchem Projekt** ein Sensor
verbaut wurde – inklusive GPS-Position und Fotos.

Diese Anwendung wird schrittweise (in Phasen) entwickelt. Jede Phase ist vollständig
lauffähig, getestet und dokumentiert. Der aktuelle Stand ist
**Phase 3 (Geräteanmeldung für Monteure)**.

## Technologie

- **Backend:** Python 3.13, Django 5.2 LTS, Django REST Framework, PostgreSQL 16, Pillow, Gunicorn
- **Frontend:** Bootstrap 5, HTML5, JavaScript (ES2023), Bootstrap Icons (später Leaflet/OpenStreetMap) – mobile first, ohne Node-Buildsystem
- **Paketverwaltung:** [uv](https://docs.astral.sh/uv/) (mit `pip`-Fallback)
- **Betrieb:** Ubuntu LTS, Nginx als Reverse Proxy, optional Docker

## Architektur in Kürze

- **Mandantentrennung (Multi-Tenancy):** Gemeinsame Datenbank, jedes Fachmodell trägt einen
  Mandanten-Fremdschlüssel. Die Trennung wird zentral durchgesetzt (siehe
  [`apps/core/tenancy.py`](apps/core/tenancy.py)): ein request-gebundener Mandantenkontext
  (via `contextvars`) plus ein Standard-Manager, der jede Abfrage automatisch auf den
  aktiven Mandanten einschränkt. **Fail-closed:** Ohne Kontext werden keine Daten geliefert,
  sondern es wird hart abgebrochen.
- **Rollen:** Superadmin (mandantenübergreifend), Mandantenadministrator, Monteur.
- **Service-Layer:** Die gesamte Geschäftslogik liegt in `services.py` je App; Views bleiben
  schlank. Änderungen werden über einen expliziten Audit-Service protokolliert.
- **Kein Django-Admin:** Alle Rollen nutzen dieselbe, mobil optimierte Oberfläche.

## Schnellstart (Entwicklung)

Voraussetzungen: `uv`, `docker` (nur für die Entwicklungsdatenbank), `git`.

```bash
# 1. Abhängigkeiten installieren (uv richtet Python 3.13 und die virtuelle Umgebung ein)
uv sync

# 2. Umgebungsdatei anlegen
cp .env.example .env

# 3. PostgreSQL für die Entwicklung starten
docker compose -f deploy/docker/docker-compose.dev.yml up -d

# 4. Datenbankschema anlegen
uv run python manage.py migrate

# 5. Ersten Superadmin anlegen
uv run python manage.py createsuperuser

# 6. Entwicklungsserver starten
uv run python manage.py runserver
```

Die Anwendung ist anschließend unter <http://127.0.0.1:8000/> erreichbar.

## Qualitätssicherung

```bash
uv run pytest            # Tests (inkl. Mandanten-Isolationstests)
uv run ruff check .      # Linting
uv run ruff format .     # Formatierung
uv run mypy .            # statische Typprüfung (strict)
```

## Projektstruktur

```
config/            Django-Projekt: Settings-Split (base/dev/prod/test), URLs, WSGI/ASGI
apps/core/         Mandant (Tenant), Mandanten-Enforcement, Middleware, Dashboard, Mandantenverwaltung
apps/accounts/     Benutzer, Rollen, Anmeldung, Benutzerverwaltung, Geräteanmeldung (QR/Token)
apps/projects/     Projekte und Benutzerzuweisungen
apps/sensors/      Sensoren und CSV-Import
apps/audit/        Audit-Log (Modell + Service)
apps/testsupport/  Hilfsmodelle – nur unter den Test-Einstellungen geladen
templates/         Django-Templates (Bootstrap 5, mobile first)
static/            CSS, JavaScript, self-hosted Vendor-Bibliotheken
deploy/            Docker-, Nginx- und systemd-Konfiguration
docs/              Installations- und Phasendokumentation
```

## Dokumentation

- [docs/INSTALL.md](docs/INSTALL.md) – Installation unter Ubuntu (mit und ohne Docker)
- [docs/PHASE-1.md](docs/PHASE-1.md) – Umfang, Entscheidungen und Tests der Phase 1
- [docs/PHASE-2.md](docs/PHASE-2.md) – Umfang, Entscheidungen und Tests der Phase 2
- [docs/PHASE-3.md](docs/PHASE-3.md) – Umfang, Entscheidungen und Tests der Phase 3
