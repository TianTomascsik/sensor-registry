# Offline-Testprotokoll (Phase 6)

Das Offline-Verhalten (Service Worker, IndexedDB, Outbox-Synchronisation) lässt sich nur in
einem echten Browser prüfen. Dieses Protokoll beschreibt die manuelle Abnahme. Empfohlen:
Google Chrome mit den DevTools (Tab „Application“ und „Network“).

Voraussetzungen:

- Die Anwendung läuft über **HTTPS** oder über `http://localhost` (Service Worker und
  Geolocation erfordern einen sicheren Kontext).
- Ein Monteur-Gerät ist registriert (siehe Phase 3), dem Monteur ist mindestens ein aktives
  Projekt zugewiesen, und es existiert mindestens ein Sensor.

## 1. Installierbarkeit / Service Worker

1. Als Monteur die Seite **Installation erfassen** öffnen.
2. DevTools → **Application → Service Workers**: Der Worker `/sw.js` ist „activated and
   running“.
3. **Application → Manifest**: Name, Icons (inkl. 512×512 und „maskable“) und `start_url`
   werden angezeigt; „Installability“ meldet keine Fehler.
4. Über das Browsermenü bzw. den Button **„App installieren“** die App zum Startbildschirm
   hinzufügen. Sie startet anschließend im Standalone-Fenster.

## 2. Referenzdaten offline verfügbar

1. Einmal **online** die Erfassungsseite öffnen (füllt das IndexedDB-Replikat).
2. DevTools → **Application → IndexedDB → papa → refdata**: Einträge `projects` und
   `sensors` sind vorhanden.
3. DevTools → **Network → Offline** aktivieren.
4. Die Erfassungsseite neu laden. Sie lädt aus dem Cache; die Auswahllisten **Projekt** und
   **Sensor** sind weiterhin gefüllt.

## 3. Offline-Erfassung

1. Bei aktivem **Offline**-Modus eine Installation erfassen:
   - Standort abwarten (Genauigkeit wird angezeigt; Warnung bei Überschreitung des
     Grenzwerts).
   - Ein oder mehrere Fotos aufnehmen/auswählen.
   - Projekt und Sensor wählen, Beschreibung eingeben.
   - **Installation speichern**.
2. Erwartung: Meldung „Offline gespeichert. Wird bei Verbindung automatisch übertragen.“
3. Unter **Meine Erfassungen** erscheint der Eintrag mit Status **wartend**.
4. DevTools → **IndexedDB → papa → outbox** enthält den Eintrag; **photos** enthält die
   (re-kodierten) Foto-Blobs.

## 4. Automatische Synchronisation

1. DevTools → **Network → Offline** deaktivieren (wieder online).
2. Innerhalb weniger Sekunden (bzw. nach Neuladen) wechselt der Eintrag über **wird
   synchronisiert** zu **erfolgreich**; die Foto-Zählung erreicht `n/n`.
3. Beim erfolgreichen Eintrag erscheint der Button **Details** und führt zur
   Installationsdetailseite (Server), inklusive der hochgeladenen Fotos.
4. Kontrolle serverseitig: Die Installation ist unter **Installationen** und auf der
   **Karte** sichtbar.

## 5. Idempotenz / kein Datenverlust

1. Während der Synchronisation kurz auf **Offline** schalten (Netzwerk unterbrechen).
2. Erwartung: Der Eintrag bleibt **wartend**/teilweise übertragen; nach erneutem Online
   wird ohne Dublette weiter- bzw. fertig synchronisiert (idempotent über `client_uuid`).

## 6. Fehlerklassen

1. **Gesperrtes Gerät:** Das Gerät im Admin-Bereich sperren, dann offline eine Erfassung
   anlegen und online gehen. Erwartung: Status **Fehler** mit Hinweis „Gerät nicht mehr
   angemeldet oder gesperrt.“ Die lokalen Daten bleiben erhalten.
2. **Validierungsfehler** (z. B. serverseitig gelöschter Sensor): Status **Fehler** mit
   Servermeldung; der Eintrag wird nicht endlos wiederholt.

## 7. Update des Service Workers

1. Eine statische Datei ändern und `collectstatic` ausführen (bzw. Assets neu ausliefern).
2. Beim nächsten Laden erscheint oben das Banner **„Eine neue Version ist verfügbar.“**
3. Auf **Aktualisieren** klicken: Die Seite lädt neu und nutzt die neue Version; alte
   Caches werden entfernt.

## Hinweise

- **iOS/Safari:** Nicht installierte Web-Apps können Website-Daten (inkl. IndexedDB) nach
  ~7 Tagen Nichtnutzung verlieren. Für den Feldeinsatz die App **zum Home-Bildschirm
  hinzufügen**. `navigator.storage.persist()` wird angefordert, ist aber nicht überall
  garantiert.
- **Kartenkacheln** (OpenStreetMap) sind offline nicht verfügbar; die Karte ist eine
  Online-Ansicht. Die Erfassung selbst funktioniert vollständig offline.
