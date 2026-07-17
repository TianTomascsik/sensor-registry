# Phase 6 – PWA & Offline

## Erklärung

Monteure arbeiten oft ohne Internet. Phase 6 macht die Anwendung zur **Progressive Web App**
und die Erfassung **offlinefähig**: Die App ist installierbar, lädt auch ohne Verbindung, hält
die zugewiesenen Projekte und Sensoren lokal vor und speichert Erfassungen in einer
**Outbox**, die automatisch synchronisiert wird, sobald wieder Internet verfügbar ist.

### Umfang dieser Phase

- **Web-App-Manifest** und Icons; installierbar auf dem Startbildschirm.
- **Service Worker** (serverseitig gerendert): Precaching der App-Shell und der statischen
  Assets, network-first-Navigationen mit Cache-Fallback, Update-Banner.
- **Offline-Replikat** (IndexedDB) der zugewiesenen Projekte und Sensoren über den neuen
  Endpunkt `/api/v1/refdata/`.
- **Offline-Outbox**: Erfassungen werden lokal abgelegt (Installation + re-kodierte Fotos)
  und idempotent gegen die REST-API synchronisiert. Statusanzeige je Eintrag: **wartend,
  wird synchronisiert, erfolgreich, Fehler**.
- **Automatische Synchronisation** beim Laden und beim `online`-Ereignis.

### Architekturentscheidungen (mit Begründung)

| Thema | Entscheidung | Begründung |
|---|---|---|
| Offline-first | Erfassungen gehen **immer** über die Outbox (nicht direkt an die API) | Einheitliches Verhalten online wie offline; kein Datenverlust bei Verbindungsabbruch; sichtbarer Status je Eintrag |
| Idempotenz | Sync nutzt die client-generierten UUIDs (Installation + Foto) | Erneutes Senden erzeugt keine Dubletten (Server antwortet 200 statt 201); Teilerfolge sind unkritisch |
| Foto-Größe | Fotos werden **clientseitig** vor dem Speichern re-kodiert (Canvas, ~2560 px, EXIF-Ausrichtung) | 8–12-MB-Kamerabilder würden die IndexedDB-Quota sprengen; die Neukodierung korrigiert zudem die Ausrichtung |
| Ein Foto pro Request | Fotos werden einzeln hochgeladen | Granulare Teilerfolge; ein fehlerhaftes Foto blockiert nicht die übrigen |
| Fehlerklassen | 4xx = dauerhafter Fehler (anzeigen), Netz/5xx = später erneut, 401/403 = „Gerät gesperrt“ | Kein Endlos-Retry bei Validierungsfehlern; robuste Wiederaufnahme bei Verbindungsproblemen |
| Parallele Syncs | `navigator.locks` um den Sync | Mehrere Tabs/Trigger synchronisieren nicht gleichzeitig; Idempotenz fängt den Rest |
| Service Worker | Serverseitig gerendert; Cache-Version = Hash der (gehashten) Precache-Liste | Der Cache erneuert sich automatisch, sobald sich Assets ändern; Update-Banner statt hartem `skipWaiting` |
| App-Shell | Erfassungsseite ohne serverseitige Daten und **ohne `{% csrf_token %}`** | Unbedenklich cachebar; das CSRF-Token liest die PWA zur Laufzeit aus dem Cookie. Für Monteure enthält die Seite keinerlei Token/Abmelde-Formular |

### Bewusste Grenzen

- **Kartenkacheln** (OpenStreetMap) sind offline nicht verfügbar; die Karte bleibt eine
  Online-Ansicht. Die Erfassung funktioniert vollständig offline.
- **iOS/Safari** kann Daten nicht installierter Web-Apps nach ~7 Tagen verwerfen; die App
  fordert `navigator.storage.persist()` an und legt die Installation auf dem Startbildschirm
  nahe.

## Verzeichnisstruktur (Ergänzungen)

```
apps/pwa/                 Manifest- und Service-Worker-Views
templates/pwa/sw.js       Service Worker (Template)
apps/installations/api.py + RefDataAPIView (/api/v1/refdata/)
static/js/pwa/            idb.js, outbox.js, register.js
static/js/capture.js      auf Offline-first (Outbox) umgestellt
static/img/               PWA-Icons (192/512/maskable/apple-touch/favicon)
```

## Tests

Ausführung: `uv run pytest` (120 Tests gesamt; 6 neu in Phase 6).

Automatisiert geprüft (Server-Verträge):

- **Manifest** wird ausgeliefert und enthält Icons inkl. maskable.
- **Service Worker**: korrekte Header (Content-Type, `Service-Worker-Allowed: /`, no-cache)
  und eingebettete Precache-Liste/Cache-Version. Zusätzlich wird der **gerenderte Service
  Worker per Node syntaktisch geprüft**.
- **Referenzdaten**: Monteure sehen nur zugewiesene Projekte + Mandanten-Sensoren,
  Administratoren alle aktiven Projekte; Mandanten-Isolation; Authentifizierungspflicht.
- Der idempotente Sync-Vertrag (Installation + Foto) ist bereits aus Phase 4 abgedeckt.

Manuell (Browser): siehe [OFFLINE-TESTPROTOKOLL.md](OFFLINE-TESTPROTOKOLL.md) – Installierbarkeit,
Offline-Erfassung, automatische Synchronisation, Idempotenz, Fehlerklassen und
Service-Worker-Update.

Qualitätswerkzeuge ohne Befund: `ruff check`, `ruff format --check`, `mypy` (strict),
`manage.py check`; alle JS-Module bestehen den Node-Syntaxcheck.

## Nächste Phase

Phase 7 ergänzt Exporte und Berichte (CSV, Excel, PDF, GPX, KML) sowie die Audit-Log-Ansicht
für Superadmins.
