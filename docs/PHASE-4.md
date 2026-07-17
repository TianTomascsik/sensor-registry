# Phase 4 – Installationen & Fotos (online)

## Erklärung

Phase 4 ist das Kernstück der Feldarbeit: Monteure erfassen vor Ort, **welcher Sensor** an
**welcher GPS-Position** in **welchem Projekt** eingebaut wurde – mit Pflichtfoto(s). Ein
Sensor kann später ausgebaut und erneut eingebaut werden; die Historie bleibt vollständig
erhalten. Administratoren können Einträge korrigieren oder stornieren.

Der Offline-/PWA-Betrieb folgt in Phase 6; Phase 4 liefert die vollständige **Online**-
Erfassung gegen die REST-API.

### Umfang dieser Phase

- **Datenmodell:** `Installation` (Sensor, Projekt, Monteur, GPS, Zeitpunkte, Status,
  Storno) und `InstallationPhoto` (Original + Thumbnail). Client-generierte UUIDs für die
  spätere idempotente Synchronisation.
- **Mobiler Erfassungsbildschirm:** automatische GPS-Bestimmung mit
  `enableHighAccuracy`, Anzeige der Genauigkeit und Warnung bei Überschreitung des
  (pro Mandant konfigurierbaren) Grenzwerts, Kamera-Aufnahme mehrerer Fotos, Beschreibung.
  Ohne gültige Position ist kein Speichern möglich.
- **Bildpipeline:** Validierung, EXIF-Ausrichtung, Neukodierung als JPEG (Original max.
  2560 px, Thumbnail 400 px), Schutz gegen Decompression-Bombs.
- **REST-API (`/api/v1/`):** idempotente Erfassung und Foto-Upload über client-UUIDs;
  Geräte-Authentifizierung per DRF-Klasse mit CSRF-Erzwingung.
- **Geschützte Medien:** Fotos sind nie öffentlich; jeder Abruf prüft die Sichtbarkeit und
  liefert die Datei per `X-Accel-Redirect` (Produktion) bzw. `FileResponse` (Entwicklung).
- **Administrative Korrektur/Storno** mit vollständigem Audit-Trail.

### Architekturentscheidungen (mit Begründung)

| Thema | Entscheidung | Begründung |
|---|---|---|
| Idempotenz | `client_uuid` je Installation/Foto, eindeutig **pro Mandant** | Grundlage für den Offline-Sync (Phase 6); erneutes Senden erzeugt keine Dubletten (200 statt 201) |
| Wiedereinbau | Beim Erfassen wird eine noch aktive Installation desselben Sensors transaktional auf „ausgebaut“ gesetzt | Ein Sensor kann umgesetzt werden; nur eine aktive Installation je Sensor (Partial-Unique-Index erzwingt dies auf DB-Ebene) |
| Storno statt Löschen | `cancelled_at` + Grund | Die Historie bleibt beweiskräftig erhalten; ein Storno gibt den Sensor wieder frei |
| Zeitpunkte | `captured_at` (Geräteuhr) getrennt von `received_at` (Serveruhr) | Die Client-Uhr ist nicht vertrauenswürdig; auditrelevant ist die Serverzeit |
| Geräte-Auth in DRF | Eigene DRF-Auth-Klasse mit CSRF-Erzwingung (analog SessionAuthentication) | DRF authentifiziert Requests eigenständig neu; Cookie-Authentifizierung ist ohne CSRF-Prüfung angreifbar. Der Runtime-Test bestätigt: Ohne CSRF-Header → 403 |
| Bild-Neukodierung | Immer serverseitig neu kodieren (statt Originaldatei speichern) | Entfernt Metadaten, korrigiert die Ausrichtung, begrenzt Größe und Angriffsfläche |
| Medienauslieferung | Django prüft Berechtigung, Nginx liefert die Bytes (`X-Accel-Redirect`) | Verbindet Zugriffsschutz mit effizienter Auslieferung; unveränderliche Fotos sind eine Woche privat cachebar |

## Verzeichnisstruktur (Ergänzungen)

```
apps/installations/
  models.py       Installation, InstallationPhoto
  imaging.py      Bildpipeline (Pillow)
  services.py     Erfassung (idempotent), Wiedereinbau, Foto, Korrektur/Storno, Abfragen
  api.py          DRF-Serializer und -Views
  api_urls.py     unter /api/v1/ gemountet
  media_views.py  geschützte Fotoauslieferung
  views.py        Erfassungsbildschirm, Liste, Detail, Korrektur/Storno
apps/accounts/authentication.py   DRF-DeviceTokenAuthentication (mit CSRF)
templates/installations/          capture, list, detail, correct, _status_badge
static/js/capture.js              Erfassungslogik (GPS, Fotos, API-Upload)
```

## Migrationen

| App | Migration | Inhalt |
|---|---|---|
| `installations` | `0001_initial` | `Installation`, `InstallationPhoto` inkl. Constraints/Indizes |
| `audit` | `0004_alter_auditlog_action` | zusätzliche Installations-Aktionen |

Anwenden mit `uv run python manage.py migrate`.

## REST-API (`/api/v1/`)

| Methode & Pfad | Zweck |
|---|---|
| `POST /installations/` | Installation erfassen (idempotent über `client_uuid`) |
| `POST /installations/<uuid>/photos/` | Foto hinzufügen (idempotent über Foto-`client_uuid`) |
| `GET /installations/list/` | Sichtbare Installationen (Suche) |
| `GET /installations/map/` | Aktive Installationen als Kartenpunkte |

Authentifizierung: Session (Admins) oder Gerätetoken-Cookie (Monteure), beide mit
CSRF-Erzwingung bei schreibenden Methoden.

## Tests

Ausführung: `uv run pytest` (107 Tests gesamt; 19 neu in Phase 4).

Schwerpunkte:

- **Bildpipeline:** Größenbegrenzung, Thumbnail, JPEG-Ausgabe, Ablehnung ungültiger Daten.
- **Services:** idempotente Erfassung, Wiedereinbau (alte Installation → ausgebaut),
  Partial-Unique (keine zwei aktiven je Sensor), Storno gibt Sensor frei, Korrektur,
  Monteur-Sichtbarkeit, Mandanten-Isolation.
- **API:** Erfassung + Idempotenz, Ablehnung nicht zugänglicher Projekte, Foto-Upload +
  Idempotenz, ungültiges Bild, Authentifizierungspflicht, Kartenendpunkt.
- **Geschützte Medien:** Zugriff für berechtigte Benutzer, 404 für fremden Mandanten.

Zusätzlich per Runtime-Test über HTTP bestätigt: Erfassung und Foto-Upload mit Gerätetoken
funktionieren, und **schreibende API-Aufrufe ohne CSRF-Header werden mit 403 abgelehnt**.

Qualitätswerkzeuge ohne Befund: `ruff check`, `ruff format --check`, `mypy` (strict),
`manage.py check`.

## Nächste Phase

Phase 5 stellt die erfassten Installationen auf einer Leaflet-Karte dar (Clustering, Popups,
Auto-Zoom) und ergänzt die globale Suche (Projekt, DevEUI, Beschreibung, Benutzer, Zeitraum)
mit `pg_trgm`-Indizes.
