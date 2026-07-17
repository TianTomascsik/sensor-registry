# Phase 7 – Exporte, Berichte & Audit-Log

## Erklärung

Phase 7 macht die dokumentierten Installationen auswertbar: Administratoren exportieren sie in
verschiedenen Formaten (Daten und Berichte), und Superadmins können das vollständige
Audit-Log einsehen. Jeder Export wird selbst wieder protokolliert.

### Umfang dieser Phase

- **Exporte** der Installationen (eines Projekts oder der aktuellen Suchergebnisse) in fünf
  Formaten:
  - **PDF-Bericht** (WeasyPrint) mit Kopf, Tabelle und Foto-Thumbnails,
  - **CSV** (Semikolon, UTF-8 mit BOM – von deutschem Excel direkt lesbar),
  - **Excel** (openpyxl),
  - **GPX** (Wegpunkte) und **KML** (Placemarks) für Karten-/GIS-Programme.
- **Berichte** für Mandantenadministratoren: der PDF-Export dient als projektbezogener
  Bericht.
- **Audit-Log-Ansicht** (nur Superadmin): filterbar nach Aktion, Benutzer, Objekt und
  Zeitraum, mit Pagination und Berücksichtigung des Mandanten-Umschalters.
- **Auditierung der Exporte:** Jeder Export erzeugt einen `EXPORT_CREATED`-Eintrag mit
  Format, Anzahl und Titel.

### Architekturentscheidungen (mit Begründung)

| Thema | Entscheidung | Begründung |
|---|---|---|
| PDF | WeasyPrint (HTML → PDF) | Fotoreiche Berichte lassen sich mit HTML/CSS deutlich einfacher gestalten als mit einer Zeichen-API; Systemabhängigkeiten sind dokumentiert |
| CSV | Semikolon + UTF-8-BOM | Öffnet in deutschem Excel ohne manuellen Import korrekt; konsistent zum CSV-Import aus Phase 2 |
| GPX/KML | Handgeschriebenes, escaptes XML | Kleine, klar definierte Formate ohne zusätzliche Abhängigkeit |
| Formatierer | Reine Funktionen ohne Request-Bezug (`formats.py`) | Gut testbar; die Orchestrierung (Datenaufbau, Audit) liegt getrennt im Service |
| Sichtbarkeit | Export nutzt dieselben mandanten-/rollengefilterten Abfragen wie Liste und Suche | Ein Export kann nie mehr Daten enthalten, als der Benutzer sehen darf |
| Audit-Log-UI | Nur Superadmin; `AuditLog` bleibt mandanten­übergreifend, wird aber je Umschalter-Auswahl gefiltert | Entspricht der Rollenvorgabe; die Gesamtsicht bleibt möglich |

## Verzeichnisstruktur (Ergänzungen)

```
apps/exports/
  formats.py   reine Formatierer (CSV/XLSX/PDF/GPX/KML)
  services.py  Datenaufbau, Orchestrierung, Audit
  views.py     Projektexport und Suchexport
templates/exports/report.html   PDF-Bericht (WeasyPrint)
apps/audit/
  views.py     Audit-Log-Ansicht (Superadmin, filterbar)
  forms.py     Filterformular
templates/audit/audit_list.html
```

## Migrationen

| App | Migration | Inhalt |
|---|---|---|
| `audit` | `0005_alter_auditlog_action` | zusätzliche Aktion `EXPORT_CREATED` |

## Zugriff

- **Exportieren** (Projektdetail und Suche): Superadmin und Mandantenadministrator.
- **Audit-Log** (Navigationspunkt): nur Superadmin.

Systemvoraussetzung für PDF: WeasyPrint benötigt Pango/Cairo (siehe
[INSTALL.md](INSTALL.md)); auf dem Zielsystem ist die Bibliothek vorhanden und der
PDF-Export wurde real erzeugt.

## Tests

Ausführung: `uv run pytest` (134 Tests gesamt; 14 neu in Phase 7).

Schwerpunkte:

- **Exportformate:** Jedes der fünf Formate liefert den korrekten Content-Type und einen
  gültigen Inhalt (u. a. `%PDF-`-Header, `<wpt>`, `<Placemark>`).
- **Isolation/Berechtigung:** fremde Projekte ⇒ 404; Monteure ⇒ 403; unbekanntes Format ⇒ 404.
- **Audit:** Exporte werden protokolliert (Format, Anzahl).
- **Audit-Log-UI:** Superadmin sieht die Einträge, Filter nach Aktion, Mandanten-Umschalter
  grenzt ein, Mandantenadministrator ⇒ 403.

Zusätzlich per Runtime-Test bestätigt: Alle fünf Formate werden über HTTP korrekt
heruntergeladen.

Qualitätswerkzeuge ohne Befund: `ruff check`, `ruff format --check`, `mypy` (strict),
`manage.py check`.

## Nächste Phase

Phase 8 schließt das Projekt ab: Nginx-Konfiguration (TLS-vorbereitet, Security-Header, CSP,
geschützte Medien via `internal`-Location), systemd-Units + Gunicorn, Docker (optional),
Ubuntu-Installationsanleitung ohne Docker, Backups und ein finaler Sicherheits-/Performance-Pass.
