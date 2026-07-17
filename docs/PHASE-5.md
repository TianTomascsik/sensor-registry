# Phase 5 – Karte & Suche

## Erklärung

Phase 5 macht die in Phase 4 erfassten Installationen auffindbar: eine interaktive
**Karte** zeigt alle aktiven Einbauten, und eine **globale Suche** findet Installationen
über mehrere Kriterien. Beides respektiert die Mandantentrennung und die rollenbasierte
Sichtbarkeit (Monteure sehen nur ihre zugewiesenen Projekte).

### Umfang dieser Phase

- **Karte** (Leaflet + OpenStreetMap, self-hosted): alle aktiven Installationen als
  gruppierte Marker (Clustering), Popups mit Foto, DevEUI, Beschreibung, Monteur und Datum,
  automatischer Zoom auf die vorhandenen Punkte.
- **Globale Suche:** Filter nach Projekt, DevEUI, Beschreibung (Freitext), Benutzer und
  Zeitraum – kombinierbar, mit Pagination.
- **Schnelle Teilstring-Suche:** PostgreSQL-Erweiterung `pg_trgm` mit GIN-Indizes auf
  Beschreibung und DevEUI.
- **Lazy Loading:** Foto-Thumbnails (Liste, Karte, Detail) werden verzögert geladen.

### Architekturentscheidungen (mit Begründung)

| Thema | Entscheidung | Begründung |
|---|---|---|
| Kartenbibliothek | Leaflet + Leaflet.markercluster, **self-hosted** | Keine CDN-Abhängigkeit zur Laufzeit (CSP-/Offline-freundlich); Clustering hält die Karte auch bei vielen Punkten performant |
| Kartendaten | Über den bestehenden API-Endpunkt `/api/v1/installations/map/` | Wiederverwendung der geprüften, mandantengefilterten Serialisierung; die Karte ist eine reine Ansicht |
| Marker-Icons | Explizite Icon-URLs via `{% static %}` statt Leaflet-Pfaderkennung | Funktioniert zuverlässig mit dem gehashten Produktions-Static-Storage (ManifestStaticFilesStorage) |
| Suche | Serverseitig gerendert (Formular + Tabelle), nicht als SPA | Einfach, robust, direkt verlinkbar; nutzt denselben Service-Layer wie Liste und API |
| Volltext | `pg_trgm` + GIN-Indizes statt einfacher `LIKE`-Scans | Schnelle, tippfehlertolerante Teilstring-Suche auch bei vielen Datensätzen |
| Kartenkacheln | OpenStreetMap-Kachelserver (externer Abruf) | Slippy-Map ohne eigenes Kacheln-Hosting; die dafür nötige CSP-Freigabe wird in Phase 8 dokumentiert |

## Verzeichnisstruktur (Ergänzungen)

```
apps/installations/
  views.py    + InstallationMapView, InstallationSearchView
  forms.py    + InstallationSearchForm
templates/installations/  map.html, search.html
static/js/    map.js (Leaflet-Karte, Clustering, Popups, Auto-Zoom)
static/vendor/leaflet/    Leaflet + Leaflet.markercluster (self-hosted)
apps/core/migrations/0002_pg_trgm.py   pg_trgm-Erweiterung
```

## Migrationen

| App | Migration | Inhalt |
|---|---|---|
| `core` | `0002_pg_trgm` | Aktiviert die PostgreSQL-Erweiterung `pg_trgm` |
| `installations` | `0002_installation_installation_desc_trgm` | GIN-Trigram-Index auf `description` |
| `sensors` | `0002_sensor_sensor_dev_eui_trgm` | GIN-Trigram-Index auf `dev_eui` |

Anwenden mit `uv run python manage.py migrate`. Die Index-Migrationen hängen automatisch von
der `pg_trgm`-Migration ab.

## Tests

Ausführung: `uv run pytest` (114 Tests gesamt; 7 neu in Phase 5).

Schwerpunkte:

- **Suche:** nach Beschreibung, DevEUI, Projekt, Benutzer und Zeitraum; Mandanten-Isolation
  (fremder Mandant liefert nichts).
- **Karte:** Datenendpunkt liefert nur aktive Installationen; Karten- und Suchseite rendern.

Zusätzlich per Runtime-Test über HTTP bestätigt: Karten- und Suchseite laden, der
Kartendaten-Endpunkt liefert die Punkte, und alle self-hosted Leaflet-Assets werden
ausgeliefert.

Qualitätswerkzeuge ohne Befund: `ruff check`, `ruff format --check`, `mypy` (strict),
`manage.py check`.

## Nächste Phase

Phase 6 macht die Erfassung offlinefähig (PWA): Service Worker, IndexedDB-Replikat der
zugewiesenen Projekte/Sensoren, Outbox-Queue mit automatischer Synchronisation und
Statusanzeige je Eintrag.
