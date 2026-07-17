# Phase 8 – Deployment & Härtung

## Erklärung

Die abschließende Phase macht die Anwendung produktiv ausrollbar: Reverse Proxy,
Anwendungsdienst, TLS-Vorbereitung, Sicherheits-Header, Docker-Option, Backups und ein
finaler Sicherheits-/Performance-Durchgang.

### Umfang dieser Phase

- **Nginx-Konfiguration** ([../deploy/nginx/papa.conf](../deploy/nginx/papa.conf)):
  TLS-vorbereitet (HTTP→HTTPS-Umleitung, Zertifikatsplatzhalter), statische Auslieferung,
  `client_max_body_size`, gzip und die **interne** Location `/_protected_media/` für die
  geschützte Fotoauslieferung via `X-Accel-Redirect`.
- **Anwendungsdienst:** Gunicorn-Konfiguration ([../deploy/gunicorn.conf.py](../deploy/gunicorn.conf.py))
  und systemd-Unit ([../deploy/systemd/papa.service](../deploy/systemd/papa.service)) mit
  Prozess-Härtung.
- **Docker (optional):** Multi-Stage-Dockerfile, Produktions-Compose (App + PostgreSQL +
  Nginx), Entrypoint (wartet auf DB, migriert, `collectstatic`), `.dockerignore`.
- **Sicherheits-Header:** strenge **Content-Security-Policy** und **Permissions-Policy**
  über `apps.core.security` (ergänzend zu Djangos `SecurityMiddleware`).
- **Backups:** Skript für konsistente DB-+Medien-Sicherung mit Aufbewahrung
  ([../deploy/backup.sh](../deploy/backup.sh)) und dokumentierte Wiederherstellung.
- **Vollständige Deployment-Anleitung:** [DEPLOY.md](DEPLOY.md).

### Sicherheitsentscheidungen (mit Begründung)

| Thema | Entscheidung | Begründung |
|---|---|---|
| CSP | Strenge Richtlinie mit `script-src 'self'` (keine Inline-Skripte/Handler) | Wirksamer XSS-Schutz. Alle bisherigen Inline-Handler (`onclick`, `onsubmit`, `onchange`) wurden durch data-Attribute + `enhance.js` ersetzt |
| CSP-Bilder | `img-src 'self' data: blob:` + OSM-Kachelserver | QR-Codes/Vorschauen/Thumbnails nutzen `data:`/`blob:`; die Karte lädt OSM-Kacheln |
| Permissions-Policy | `geolocation=(self)`, übrige Sensoren gesperrt | Die Erfassung braucht Geolocation; alles andere wird deaktiviert |
| Header in Django | CSP/Permissions-Policy in der Middleware, nicht nur in Nginx | Portabel (Docker wie systemd), testbar, unabhängig vom Proxy |
| Geschützte Medien | Nginx `internal`-Location + `X-Accel-Redirect` | Zugriffsschutz (Django prüft) plus effiziente Auslieferung (Nginx liefert) |
| Docker als Option | Anwendung läuft auch ohne Docker vollständig | Vorgabe: „Docker soll optional unterstützt werden“ |

### Vom finalen Durchgang gefundener und behobener Produktionsfehler

`collectstatic` mit `ManifestStaticFilesStorage` schlug fehl, weil vendored Minified-Dateien
`sourceMappingURL`-Kommentare auf nicht vorhandene `.map`-Dateien enthielten. Diese Kommentare
wurden aus den self-hosted Assets entfernt; `collectstatic` verarbeitet nun alle 64 Dateien
fehlerfrei, und die gehashten URLs (inkl. CSS-`url()`-Umschreibungen für Leaflet-Bilder)
lösen korrekt auf.

## Verzeichnisstruktur (Ergänzungen)

```
deploy/
  nginx/papa.conf            Nginx (ohne Docker)
  gunicorn.conf.py           Gunicorn-Parameter
  systemd/papa.service       systemd-Unit
  backup.sh                  Backup-Skript (DB + Medien)
  docker/
    Dockerfile               Multi-Stage-Image
    entrypoint.sh            Migrationen + collectstatic + Start
    docker-compose.prod.yml  App + PostgreSQL + Nginx
    nginx.conf               Nginx im Compose-Setup
apps/core/security.py        SecurityHeadersMiddleware (CSP, Permissions-Policy)
static/js/enhance.js         Progressive Enhancement ohne Inline-Handler
docs/DEPLOY.md               vollständige Deployment-Anleitung
```

## Tests

Ausführung: `uv run pytest` (137 Tests gesamt; 3 neu in Phase 8).

Schwerpunkte:

- **Sicherheits-Header:** CSP wird gesetzt, `script-src` ist strikt (kein `'unsafe-inline'`),
  OSM-Kacheln erlaubt; Permissions-Policy gibt Geolocation frei und sperrt die Kamera.

Zusätzlich geprüft:

- **`manage.py check --deploy`** meldet mit gültigem `SECRET_KEY` **keine** Probleme.
- **`collectstatic`** (Produktions-Storage) läuft fehlerfrei; gehashte URLs lösen auf.
- Runtime über HTTP: CSP-/Permissions-Policy-Header vorhanden, `enhance.js` ausgeliefert,
  alle Seiten funktionieren mit den data-Attributen (kein Inline-JS mehr).

Qualitätswerkzeuge ohne Befund: `ruff check`, `ruff format --check`, `mypy` (strict).

## Projektstand

Mit Phase 8 sind **alle acht Phasen** abgeschlossen. Die Anwendung ist funktional vollständig,
getestet, dokumentiert und produktiv ausrollbar – sowohl klassisch (systemd + Nginx) als auch
per Docker.
