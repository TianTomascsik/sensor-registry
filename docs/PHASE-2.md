# Phase 2 – Projekte & Sensoren

## Erklärung

Phase 2 ergänzt die ersten produktiven Fachdaten: **Projekte** (mit Benutzerzuweisungen)
und **Sensoren** (mit CSV-Massenimport). Es sind zugleich die ersten mandantengebundenen
Modelle – die in Phase 1 aufgebaute Mandantentrennung wird damit an echten Daten wirksam
und getestet.

### Umfang dieser Phase

- **Projekte:** Anlegen, Bearbeiten und Ansehen. Ein Projekt hat Projektnummer (eindeutig je
  Mandant), Name, Kunde, Beschreibung, Status (aktiv / abgeschlossen / archiviert) und
  Erstellungsdatum.
- **Benutzerzuweisung:** Administratoren weisen Projekten Benutzer zu bzw. entfernen sie.
  **Monteure sehen ausschließlich die ihnen zugewiesenen Projekte**; Administratoren sehen
  alle Projekte ihres Mandanten.
- **Sensoren:** Stammdatenverwaltung (DevEUI, Hersteller, Typ, Seriennummer, Bemerkung).
  Der DevEUI wird normalisiert (16 Hexzeichen, Großschreibung, Trennzeichen entfernt) und ist
  je Mandant eindeutig.
- **CSV-Import:** Fehlertoleranter Massenimport von Sensorlisten mit automatischer Erkennung
  von Kodierung (inkl. BOM) und Trennzeichen (Komma/Semikolon), flexibler Spaltenzuordnung
  (deutsche und englische Überschriften), Duplikatbehandlung und strukturiertem Fehlerbericht.
- **Listen:** Suche und Pagination für Projekte und Sensoren.
- **Audit:** Alle Projekt-/Sensor-Aktionen (Anlegen, Ändern, Löschen, Zuweisen, Import)
  werden protokolliert.

### Architekturentscheidungen (mit Begründung)

| Thema | Entscheidung | Begründung |
|---|---|---|
| Eindeutigkeit | Projektnummer und DevEUI eindeutig **pro Mandant** (zusammengesetzter Unique-Constraint mit `tenant`) | Verschiedene Firmen dürfen dieselbe Nummer/denselben DevEUI führen; innerhalb einer Firma nicht |
| Zuweisung | Explizites Zwischenmodell `ProjectAssignment` (statt automatischer M2M-Tabelle) | Auch die Zuweisung ist mandantengebunden und protokollierbar; die automatische M2M-Tabelle hätte keinen Mandanten-FK und würde den Mandanten-System-Check verletzen |
| CSV-Import | Fehlertolerant (gültige Zeilen anlegen, Rest berichten) statt Alles-oder-nichts | Eine einzelne fehlerhafte Zeile darf den Import einer großen Liste nicht verhindern; der Bericht macht Probleme transparent |
| DevEUI-Normalisierung | Zentral in `Sensor.save()` und `normalize_deveui()` | Garantiert, dass die Eindeutigkeit unabhängig von der Schreibweise der Eingabe greift; `bulk_create` im Import normalisiert daher explizit vorab |
| Sichtbarkeit | Im Service-Layer (`visible_projects`) statt in der View | Einheitliche, testbare Regel; die Mandantentrennung bleibt zusätzlich über den `TenantManager` erzwungen |
| Generischer Manager | `TenantManager`/`TenantQuerySet` als generische Typen (`TypeVar`) | So liefern `Project.objects`/`Sensor.objects` den konkreten Modelltyp – wichtig für die strikte Typprüfung |

## Verzeichnisstruktur (Ergänzungen)

```
apps/
  projects/     Project, ProjectAssignment, Service (Sichtbarkeit/Zuweisung), Views, Forms, URLs, Tests
  sensors/      Sensor, Service (Verwaltung + CSV-Import), Views, Forms, URLs, Tests
templates/
  projects/     project_list/detail/form + _status_badge
  sensors/      sensor_list/form/import
  includes/     _search.html (wiederverwendbare Suchleiste)
```

## Migrationen

| App | Migration | Inhalt |
|---|---|---|
| `projects` | `0001_initial` | `Project`, `ProjectAssignment` inkl. Unique-Constraints und Index |
| `sensors` | `0001_initial` | `Sensor` inkl. Unique-Constraint (Mandant + DevEUI) und Index |
| `audit` | `0002_alter_auditlog_action` | zusätzliche Aktionen (Projekte/Sensoren/Import) |

Anwenden mit `uv run python manage.py migrate`.

## CSV-Import – Format

Erste Zeile = Kopfzeile. Nur eine **DevEUI**-Spalte ist Pflicht; weitere Spalten sind
optional. Erkannte Überschriften (Groß-/Kleinschreibung und Trennzeichen egal):

| Feld | Erkannte Überschriften |
|---|---|
| DevEUI | `DevEUI`, `EUI` |
| Hersteller | `Hersteller`, `Manufacturer` |
| Typ | `Typ`, `Type`, `Sensortyp` |
| Seriennummer | `Seriennummer`, `Serial`, `SN` |
| Bemerkung | `Bemerkung`, `Note`, `Notiz`, `Kommentar` |

Beispiel:

```csv
DevEUI,Hersteller,Typ,Seriennummer,Bemerkung
70B3D57ED0012345,Dragino,LSE01,SN-1,Feld A
70:B3:D5:7E:D0:01:23:46,Milesight,EM500,SN-2,Feld B
```

Der Bericht weist aus: angelegt, bereits vorhanden, doppelt in Datei, fehlerhaft (mit
Zeilennummer und Grund).

## Tests

Ausführung: `uv run pytest` (67 Tests gesamt; 31 neu in Phase 2).

Schwerpunkte der neuen Tests:

- **Mandanten-Isolation an echten Modellen:** gleiche Projektnummer/DevEUI in verschiedenen
  Mandanten erlaubt, im selben Mandanten abgelehnt; fremde Projekte/Sensoren liefern 404.
- **Projekte:** CRUD, doppelte Nummer abgelehnt, Monteur sieht nur zugewiesene Projekte und
  kann fremde nicht öffnen/verwalten, Zuweisen/Entfernen (idempotent), Suche.
- **Sensoren:** DevEUI-Normalisierung, Eindeutigkeit je Mandant, CRUD, Löschen,
  Berechtigungen, Suche.
- **CSV-Import:** gültiger Import, Semikolon-Trennzeichen, Duplikate in Datei, bereits
  vorhandene Sensoren, ungültige Zeilen im Fehlerbericht, fehlende DevEUI-Spalte,
  Mandantentrennung, Import über die View.

Qualitätswerkzeuge (alle ohne Befund):

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run python manage.py check
```

## Nächste Phase

Phase 3 ergänzt die passwortlose **Geräteanmeldung für Monteure** (QR-Code/Einladungslink,
Gerätetoken, Sperren verlorener Geräte) als Grundlage für die mobile Installationserfassung.
