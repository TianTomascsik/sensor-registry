# Phase 3 – Passwortlose Geräteanmeldung für Monteure

## Erklärung

Monteure arbeiten im Feld und sollen sich **ohne Passwort dauerhaft** anmelden können. Ein
Administrator erzeugt dazu einen Einladungslink bzw. QR-Code; beim ersten Öffnen registriert
sich das Gerät und bleibt anschließend angemeldet. Verlorene oder ausgemusterte Geräte kann
der Administrator einzeln sperren – der Zugriff endet sofort.

### Ablauf

1. **Einladung erstellen** (Administrator): Für einen Monteur wird eine einmalige, ablaufende
   Einladung erzeugt. Der Klartext-Token erscheint nur einmal – als Link und als QR-Code.
2. **Gerät registrieren** (Monteur, ohne Anmeldung): Der Monteur öffnet den Link auf seinem
   Gerät und bestätigt. Dabei entsteht ein dauerhafter Gerätetoken, der als HttpOnly-Cookie
   (~1 Jahr) gespeichert wird.
3. **Dauerhafte Anmeldung**: Jeder weitere Request authentifiziert das Gerät anhand des
   Cookies. Der Monteur sieht ohne erneute Anmeldung seine zugewiesenen Projekte.
4. **Sperren/Entfernen** (Administrator): Ein gesperrtes Gerät verliert beim nächsten Request
   sofort den Zugriff.

### Sicherheitsdesign (mit Begründung)

| Thema | Entscheidung | Begründung |
|---|---|---|
| Token-Speicherung | Nur **SHA-256-Hash** in der Datenbank; Klartext nur im Cookie/Link | Ein Datenbankleck gibt keine gültigen Tokens preis |
| Token-Stärke | 256 Bit (`secrets.token_urlsafe(32)`) | Nicht erratbar |
| Einlösung | **Atomar** per bedingtem UPDATE (`used_at`/`expires_at`) | Verhindert Doppel-Einlösung derselben Einladung (Race Condition) |
| Auth als Middleware | Geräteauthentifizierung in Django-Middleware, **nicht** nur als DRF-Auth-Klasse | DRF authentifiziert erst in `APIView.initial()` – also nach der Mandanten-Middleware. Nur die Django-Middleware setzt `request.user` früh genug, damit der Mandantenkontext daraus abgeleitet werden kann |
| Reihenfolge | Session → Auth → **DeviceToken** → Tenant | Eine bestehende Admin-Session wird nie überschrieben; der Mandant wird nach der Geräteauthentifizierung gesetzt |
| Sofortige Sperrung | Prüfung des `revoked_at` bei **jedem** Request (DB-geprüfter Token, kein JWT) | Ein verlorenes Gerät verliert sofort den Zugriff – bei JWT strukturell nicht möglich |
| Cookie | HttpOnly, SameSite=Lax; in Produktion `__Host-`-Präfix (Secure, Path=/, ohne Domain) | Schutz vor XSS-Auslesen und CSRF-Missbrauch; CSRF wird zusätzlich von Djangos CsrfViewMiddleware erzwungen |
| `last_seen` | Aktualisierung höchstens einmal je 15 Minuten (bedingtes UPDATE) | Kein Datenbank-Write pro Request |
| Einmalanzeige | Der Einladungslink wird nur einmal angezeigt (Klartext-Token via Session an die Anzeige-Seite) | Da nur der Hash gespeichert wird, ist der Link später nicht rekonstruierbar – bewusst; verloren = neu erstellen |

Monteure haben bewusst **keine Selbst-Abmeldung** (dauerhafte Anmeldung ist gewünscht);
die Kontrolle über Geräte liegt beim Administrator.

## Verzeichnisstruktur (Ergänzungen)

```
apps/accounts/
  models.py         + DeviceInvite, Device
  devices.py        Service: Token/Hash, Einladung, Einlösung, Auth, last_seen, Cookie, QR
  middleware.py     DeviceTokenMiddleware (Cookie-Authentifizierung)
  device_views.py   Registrierung (anonym) + Geräteverwaltung (Admin)
  device_urls.py    unter /geraete/ gemountet
templates/devices/  register(_invalid), device_list, invite_form, invite_show
static/js/          invite_copy.js (Link kopieren, ohne Inline-Skript)
```

## Migrationen

| App | Migration | Inhalt |
|---|---|---|
| `accounts` | `0002_deviceinvite_device` | `DeviceInvite`, `Device` |
| `audit` | `0003_alter_auditlog_action` | zusätzliche Geräte-Aktionen |

Anwenden mit `uv run python manage.py migrate`.

## Konfiguration

In `config/settings/base.py` (Standardwerte, per Umgebung überschreibbar):

- `DEVICE_TOKEN_COOKIE_NAME` – Cookie-Name (Produktion: `__Host-device_token`)
- `DEVICE_TOKEN_COOKIE_MAX_AGE` – Lebensdauer des Gerätetokens (Standard ~1 Jahr)
- `DEVICE_INVITE_TTL_DAYS` – Gültigkeit einer Einladung (Standard 14 Tage)
- `DEVICE_LAST_SEEN_THROTTLE_SECONDS` – Drosselung von `last_seen` (Standard 900 s)

## Tests

Ausführung: `uv run pytest` (88 Tests gesamt; 21 neu in Phase 3).

Schwerpunkte:

- **Einladung/Service:** nur für Monteure; atomare Einlösung; Token-Hashing.
- **Registrierungs-Flow:** Bestätigungsseite, ungültiger/abgelaufener/benutzter Token (400),
  erfolgreiche Registrierung setzt Cookie und legt Gerät an, **keine Doppel-Einlösung**.
- **Geräteauthentifizierung:** Zugriff allein per Cookie als Monteur (sieht zugewiesene
  Projekte); **Sperren wirkt sofort**; inaktiver Benutzer/Mandant sperrt; Admin-Session hat
  Vorrang vor dem Gerätecookie.
- **`last_seen`-Drosselung**, **Mandanten-Isolation** (fremdes Gerät ⇒ 404),
  **Berechtigungen** (Monteur ⇒ 403; Superadmin ohne Mandantenauswahl ⇒ Hinweis).

Qualitätswerkzeuge (ohne Befund): `ruff check`, `ruff format --check`, `mypy` (strict),
`manage.py check`.

## Bewusste Abgrenzung

Eine **Token-Rotation mit Überlappungsfenster** wurde für Phase 3 bewusst weggelassen: Ohne
Rotation gibt es kein Aussperr-Risiko durch verlorene Rotations-Antworten. Sie bleibt als
optionale Härtung für Phase 8 vorgemerkt. Die **DRF-Authentifizierungsklasse** (mit
CSRF-Erzwingung) folgt in Phase 4 zusammen mit den ersten API-Endpunkten, an denen sie
integrationsgetestet werden kann.

## Nächste Phase

Phase 4 bringt die mobile Installationserfassung: `/api/v1`-Grundstock, GPS-Erfassung mit
Genauigkeitswarnung, Pflichtfotos mit Bildpipeline und geschützte Medienauslieferung.
