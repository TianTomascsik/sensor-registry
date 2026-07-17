# Phase 1 – Fundament

## Erklärung

Phase 1 legt das tragfähige Fundament der Anwendung. Alles Weitere (Projekte, Sensoren,
Installationen, Karte, Offline/PWA, Exporte) baut darauf auf. Der Schwerpunkt liegt auf dem
sicherheitskritischen Kern: der **strikten Trennung der Mandanten** und der
**Benutzer-/Rollenverwaltung** samt revisionssicherer Protokollierung.

### Umfang dieser Phase

- **Projektgerüst:** Django 5.2 unter Python 3.13, verwaltet mit `uv`; Settings-Split in
  `base`/`dev`/`prod`/`test`; Konfiguration ausschließlich über Umgebungsvariablen/`.env`.
- **Mandant (Tenant):** Stammdaten inkl. konfigurierbarer GPS-Genauigkeitsgrenze
  (Standard 5 m) und Aktiv-/Inaktiv-Status.
- **Mandanten-Enforcement (fail-closed):** request-gebundener Mandantenkontext über
  `contextvars`, ein Standard-Manager, der jede Abfrage automatisch auf den aktiven
  Mandanten einschränkt, sowie eine Model-Basisklasse, die beim Speichern den Mandanten
  setzt bzw. Cross-Tenant-Schreibzugriffe verhindert. Ein eigener Django-System-Check
  erzwingt, dass jedes neue Fachmodell seine Mandantenbindung bewusst deklariert.
- **Benutzer & Rollen:** eigenes Benutzermodell (Anmeldung per E-Mail), drei Rollen
  (Superadmin, Mandantenadministrator, Monteur). Anmeldung mit Rate-Limit gegen
  Brute-Force. Ein deaktivierter Mandant sperrt die Anmeldung all seiner Benutzer.
- **Verwaltungsoberfläche (mobile first, Bootstrap 5):** Mandantenverwaltung (Superadmin)
  mit Mandanten-Umschalter für die Gesamtsicht; Benutzerverwaltung (Superadmin und
  Mandantenadministrator) mit Anlegen, Bearbeiten und (De-)Aktivieren.
- **Audit-Log:** expliziter Service protokolliert Anmeldung, Abmeldung, fehlgeschlagene
  Anmeldung sowie alle Mandanten- und Benutzeränderungen mit Zeit, Benutzer, IP,
  User-Agent, Aktion, Objekt und Vorher/Nachher-Werten.

### Zentrale Architekturentscheidungen (mit Begründung)

| Thema | Entscheidung | Begründung |
|---|---|---|
| Mandantentrennung | Gemeinsame DB, Mandanten-FK je Modell, zentrale Durchsetzung | Einfache Migrationen/Backups, mühelose Superadmin-Gesamtsicht; die Isolation wird zentral erzwungen und flächendeckend getestet |
| Fail-closed | Fehlender Kontext ⇒ harte Ausnahme statt „alle Daten“ | Ein vergessener Filter darf niemals stillschweigend fremde Mandantendaten preisgeben |
| Base-Manager | `Meta.base_manager_name = "unscoped"` (ungefiltert) | Djangos interne Operationen (FK-Prüfung, `refresh_from_db`, Löschkaskaden) dürfen nicht mandantengefiltert laufen |
| Kein Django-Admin | Eigene Bootstrap-Oberfläche für alle Rollen | Einheitliches, mobil optimiertes Bedienkonzept; kleinere Angriffsfläche |
| Audit explizit | Service-Aufrufe statt automatischer Middleware | Jedes protokollierte Ereignis ist nachvollziehbar und testbar an genau einer Stelle ausgelöst |

## Verzeichnisstruktur (Phase 1)

```
config/
  settings/{base,dev,prod,test}.py   Umgebungskonfiguration
  urls.py  wsgi.py  asgi.py
apps/
  core/          Tenant, tenancy.py (contextvars/Manager/Basisklasse), Middleware,
                 System-Check, Dashboard, Mandantenverwaltung, Kontextprozessor
  accounts/      Benutzermodell, Rollen, Auth-Backend, Anmeldung, Benutzerverwaltung, Signale
  audit/         AuditLog-Modell und Audit-Service
  testsupport/   Hilfsmodell (nur unter config.settings.test geladen)
templates/       base.html (mobile first) + Seiten je App + Fehlerseiten
static/          css/app.css, self-hosted Bootstrap & Bootstrap Icons
deploy/docker/   docker-compose.dev.yml (Entwicklungsdatenbank)
docs/            INSTALL.md, PHASE-1.md
```

## Installation

Siehe [INSTALL.md](INSTALL.md). Kurzfassung für die Entwicklung:

```bash
uv sync
cp .env.example .env
docker compose -f deploy/docker/docker-compose.dev.yml up -d
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

## Migrationen

| App | Migration | Inhalt |
|---|---|---|
| `core` | `0001_initial` | Modell `Tenant` |
| `accounts` | `0001_initial` | Modell `User` inkl. Rollen und Rollen-/Mandanten-Konsistenzbedingung |
| `audit` | `0001_initial` | Modell `AuditLog` mit Indizes |
| `testsupport` | `0001_initial` | Testhilfsmodell (nur Testdatenbank) |

Anwenden mit `uv run python manage.py migrate`. Das Schema ist auf einer frischen Datenbank
vollständig reproduzierbar.

## Tests

Ausführung: `uv run pytest` (36 Tests).

Schwerpunkte:

- **Mandanten-Isolation** (`apps/core/tests/test_tenancy.py`): Zugriff ohne Kontext schlägt
  hart fehl; Abfragen werden korrekt auf den aktiven Mandanten gefiltert; der Systemkontext
  sieht alle; das Speichern setzt den Mandanten bzw. verhindert Cross-Tenant-Writes; der
  ungefilterte Base-Manager wird korrekt vererbt.
- **Anmeldung** (`apps/accounts/tests/test_login.py`): Erfolg, falsches Passwort
  (protokolliert), gesperrter Mandant verhindert Anmeldung, Rate-Limit, Abmeldung nur per POST.
- **Benutzerverwaltung** (`apps/accounts/tests/test_user_management.py`): Mandantenadmins
  sehen und bearbeiten ausschließlich eigene Benutzer (fremde ⇒ 404); Anlegen/Deaktivieren;
  Superadmin-Mandantenauswahl; Monteure haben keinen Zugriff auf die Verwaltung.
- **Mandantenverwaltung** (`apps/core/tests/test_tenant_management.py`): Anlegen/Ändern,
  doppeltes Kürzel abgelehnt, Umschalter, Rollen- und Anmeldeprüfungen.
- **Audit** (`apps/audit/tests/test_audit.py`): Ableitung des Mandanten, IP/User-Agent-Erfassung,
  Sortierung.

### Qualitätswerkzeuge

```bash
uv run ruff check .        # Linting: keine Befunde
uv run ruff format --check # Formatierung: konsistent
uv run mypy .              # statische Typprüfung (strict): keine Fehler
uv run python manage.py check   # Django-System-Checks: keine Probleme
```

## Nächste Phase

Phase 2 ergänzt Projekte und Sensoren (inkl. CSV-Import) sowie die ersten echten
mandantengebundenen Fachmodelle – und damit Mandanten-Isolationstests an produktiven
Modellen.
