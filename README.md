# Sensor-Dokumentation

Mandantenfähige Webanwendung zur Dokumentation von LoRaWAN-Bodensensor-Installationen:
Sie hält fest, **wo, wann, durch welchen Monteur und in welchem Projekt** ein Sensor
verbaut wurde – inklusive GPS-Position und Fotos.

Diese Anwendung wurde schrittweise in acht Phasen entwickelt. Jede Phase ist vollständig
lauffähig, getestet und dokumentiert. **Alle acht Phasen sind abgeschlossen**; die Anwendung
ist funktional vollständig und produktiv ausrollbar (siehe [docs/DEPLOY.md](docs/DEPLOY.md)).

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

# 5. Entwicklungskonten und Demodaten anlegen (idempotent, nur unter DEBUG)
uv run python manage.py seed_dev

# 6. Entwicklungsserver starten
uv run python manage.py runserver
```

Die Anwendung ist anschließend unter <http://127.0.0.1:8000/> erreichbar.

### Entwicklungskonten (`seed_dev`)

`seed_dev` legt je ein Konto pro Rolle sowie ein Demo-Projekt, einen Demo-Sensor und die
zugehörige Projektzuweisung an (der Monteur sieht das Projekt nur, weil er ihm zugewiesen
ist). Der Befehl ist idempotent – wiederholtes Ausführen aktualisiert nur und setzt die
Passwörter zurück. Zum Schutz vor schwachen Passwörtern verweigert er die Ausführung
außerhalb von `DEBUG` (Umgehung nur mit `--force`, Passwort per `--password`).

| Rolle | E-Mail | Mandant | Passwort |
| --- | --- | --- | --- |
| Superadmin | `superadmin@dev.local` | – | `dev12345` |
| Mandantenadministrator | `admin@dev.local` | Demo GmbH | `dev12345` |
| Monteur | `monteur@dev.local` | Demo GmbH | `dev12345` |

Zum Testen der mobilen Erfassung als **`monteur@dev.local`** anmelden – dieser hat einen
festen Mandanten, sodass der Mandantenkontext gesetzt ist. Alternativ legt
`uv run python manage.py createsuperuser` nur einen einzelnen Superadmin an (ohne Demodaten).

## Kartenkacheln (Tile-Quelle)

Die Kartenansicht (Leaflet) lädt ihre Kacheln über eine konfigurierbare Tile-Quelle. Sie ist
per Umgebungsvariablen einstellbar:

| Variable | Bedeutung | Default |
| --- | --- | --- |
| `MAP_TILE_URL` | Kachel-URL im Leaflet-Schema (`{s}` = Subdomain, optional; `{z}/{x}/{y}`) | OpenStreetMap |
| `MAP_TILE_ATTRIBUTION` | Quellennachweis am Kartenrand (HTML erlaubt, z. B. `&copy;`) | `&copy; OpenStreetMap-Mitwirkende` |
| `MAP_TILE_MAX_ZOOM` | maximale Zoomstufe | `19` |

**Warum nicht einfach OpenStreetMap?** OSMs Volunteer-Tile-Server dürfen laut
[Nutzungsrichtlinie](https://operations.osmfoundation.org/policies/tiles/) nicht produktiv
genutzt werden und blocken solche Zugriffe – u. a. mit `HTTP 403` („Access blocked – Referer
is required"), besonders **beim Zoomen**, wenn viele Kacheln gleichzeitig geladen werden. Die
App sendet zwar pro Kachel einen Referer (nötig wegen der globalen `Referrer-Policy:
same-origin`), das umgeht aber nur die Referer-Sperre, nicht die Mengenbegrenzung. Für alles
außer leichtem Ausprobieren daher eine eigene Quelle setzen.

### Anbieter-Beispiele

Ohne API-Key (Entwicklung / leichte Nutzung – Attribution beachten):

```bash
# CARTO (OSM-basiert, schlüsselfrei) – Default in der mitgelieferten .env
MAP_TILE_URL=https://{s}.basemap.cartocdn.com/light_all/{z}/{x}/{y}.png
MAP_TILE_ATTRIBUTION=&copy; OpenStreetMap-Mitwirkende &copy; CARTO
MAP_TILE_MAX_ZOOM=20
```

Mit API-Key (empfohlen für Produktion):

```bash
# MapTiler
MAP_TILE_URL=https://api.maptiler.com/maps/streets/{z}/{x}/{y}.png?key=DEIN_KEY
MAP_TILE_ATTRIBUTION=&copy; MapTiler &copy; OpenStreetMap-Mitwirkende

# Thunderforest
MAP_TILE_URL=https://{s}.tile.thunderforest.com/atlas/{z}/{x}/{y}.png?apikey=DEIN_KEY
MAP_TILE_ATTRIBUTION=&copy; Thunderforest &copy; OpenStreetMap-Mitwirkende
```

Eigener Tile-Server (volle Kontrolle, kein Drittanbieter): z. B. das Docker-Image
`overv/openstreetmap-tile-server` betreiben und
`MAP_TILE_URL=https://tiles.example.com/{z}/{x}/{y}.png` setzen.

> **Nach einer Änderung:** `.env` wird nur beim Start gelesen → Dev-Server neu starten. Und
> `static/js/map.js` liegt im Service-Worker-Cache → die Karte einmal **hart neu laden** (bzw.
> die PWA schließen und neu öffnen), damit die neue Quelle greift.

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
apps/installations/ Installationen, Fotos, REST-API (/api/v1), geschützte Medien
apps/pwa/          Web-App-Manifest und Service Worker (Offline-Betrieb)
apps/exports/      Exporte (CSV, Excel, PDF, GPX, KML)
apps/audit/        Audit-Log (Modell, Service, Superadmin-Ansicht)
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
- [docs/PHASE-4.md](docs/PHASE-4.md) – Umfang, Entscheidungen und Tests der Phase 4
- [docs/PHASE-5.md](docs/PHASE-5.md) – Umfang, Entscheidungen und Tests der Phase 5
- [docs/PHASE-6.md](docs/PHASE-6.md) – Umfang, Entscheidungen und Tests der Phase 6
- [docs/PHASE-7.md](docs/PHASE-7.md) – Umfang, Entscheidungen und Tests der Phase 7
- [docs/PHASE-8.md](docs/PHASE-8.md) – Umfang, Entscheidungen und Tests der Phase 8
- [docs/DEPLOY.md](docs/DEPLOY.md) – Produktions-Deployment (systemd/Nginx und Docker), TLS, Backups
- [docs/OFFLINE-TESTPROTOKOLL.md](docs/OFFLINE-TESTPROTOKOLL.md) – manuelle Offline-Abnahme
