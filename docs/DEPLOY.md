# Produktions-Deployment & Härtung

Diese Anleitung beschreibt den produktiven Betrieb. Grundlagen (Systempakete, Datenbank,
`.env`) stehen in [INSTALL.md](INSTALL.md); hier folgen Reverse Proxy, Anwendungsdienst,
TLS, geschützte Medien, Sicherheit und Backups.

Es gibt zwei gleichwertige Wege:

1. **Ohne Docker** – Gunicorn als systemd-Dienst hinter Nginx (empfohlen für einen dedizierten Server).
2. **Mit Docker** – App, PostgreSQL und Nginx per Compose (optional).

---

## 1. Betrieb ohne Docker (systemd + Nginx)

### 1.1 Anwendung bereitstellen

Wie in [INSTALL.md](INSTALL.md) Abschnitt 2: Repository nach `/srv/papa`, `uv sync --no-dev`
(oder `pip install -r requirements.txt`), `.env` mit **`DJANGO_ENV=prod`** und einem sicheren
`DJANGO_SECRET_KEY` anlegen.

Wichtige `.env`-Werte für Produktion:

```ini
DJANGO_ENV=prod
DJANGO_SECRET_KEY=<zufällig, 64+ Zeichen>
DJANGO_ALLOWED_HOSTS=app.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://app.example.com
DATABASE_URL=postgres://papa:PASSWORT@127.0.0.1:5432/papa
DJANGO_SECURE_SSL=1
MEDIA_SERVE_BACKEND=accel
MEDIA_ACCEL_LOCATION=/_protected_media/
```

### 1.2 Schema, statische Dateien, Superadmin

```bash
export DJANGO_ENV=prod
uv run python manage.py migrate
uv run python manage.py collectstatic --noinput
uv run python manage.py createsuperuser
```

### 1.3 Anwendungsdienst (Gunicorn via systemd)

```bash
sudo useradd --system --home /srv/papa papa   # falls noch nicht vorhanden
sudo chown -R papa:papa /srv/papa
sudo cp deploy/systemd/papa.service /etc/systemd/system/papa.service
sudo systemctl daemon-reload
sudo systemctl enable --now papa
sudo systemctl status papa
```

Die Gunicorn-Parameter (Worker, Timeout) stehen in `deploy/gunicorn.conf.py`.

### 1.4 Nginx als Reverse Proxy

```bash
sudo cp deploy/nginx/papa.conf /etc/nginx/sites-available/papa
sudo ln -s /etc/nginx/sites-available/papa /etc/nginx/sites-enabled/papa
# server_name und Verzeichnisse anpassen; danach:
sudo nginx -t && sudo systemctl reload nginx
```

Die Konfiguration liefert statische Dateien direkt aus, reicht die Anwendung an Gunicorn
weiter und stellt die **interne** Location `/_protected_media/` für die geschützte
Fotoauslieferung bereit (Django prüft die Berechtigung und antwortet mit `X-Accel-Redirect`).

### 1.5 TLS (Let's Encrypt)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d app.example.com
```

Certbot trägt die Zertifikatspfade ein und richtet die Erneuerung ein. Mit `DJANGO_SECURE_SSL=1`
erzwingt Django HTTPS, setzt sichere Cookies und HSTS.

---

## 2. Betrieb mit Docker (optional)

```bash
cp .env.example .env            # DJANGO_SECRET_KEY und DJANGO_ALLOWED_HOSTS setzen
docker compose -f deploy/docker/docker-compose.prod.yml up -d --build
# Ersten Superadmin anlegen:
docker compose -f deploy/docker/docker-compose.prod.yml exec app python manage.py createsuperuser
```

Der App-Container wartet auf die Datenbank, migriert und sammelt beim Start automatisch die
statischen Dateien (siehe `deploy/docker/entrypoint.sh`). Nginx läuft auf Port 80 und liefert
statische Dateien sowie geschützte Medien aus geteilten Volumes.

TLS: Das Compose-Setup terminiert kein TLS. Für Produktion entweder Zertifikate in den
Nginx-Container einbinden oder einen vorgelagerten TLS-Proxy verwenden und dort
`X-Forwarded-Proto: https` setzen (dann in der `.env` `DJANGO_SECURE_SSL=1`).

---

## 3. Sicherheit

- **`manage.py check --deploy`** ausführen – meldet unter `prod` keine Probleme:
  ```bash
  DJANGO_ENV=prod uv run python manage.py check --deploy
  ```
- **Sicherheits-Header:** HSTS, `X-Content-Type-Options`, Referrer-Policy und
  Cross-Origin-Opener-Policy setzt Djangos `SecurityMiddleware`; eine strenge
  **Content-Security-Policy** (`script-src 'self'`) und eine **Permissions-Policy**
  (Geolocation nur für die eigene Herkunft) ergänzt `apps.core.security`.
- **Geheimnisse:** `DJANGO_SECRET_KEY` niemals committen; die `.env` ist in `.gitignore`.
- **Uploads:** durch `client_max_body_size` (Nginx) und `DATA_UPLOAD_MAX_MEMORY_SIZE` (Django)
  begrenzt; Bilder werden serverseitig neu kodiert.
- **Rate Limiting** für die Anmeldung ist aktiv (Phase 1).

## 4. Backups

Datenbank **und** Medienverzeichnis konsistent sichern:

```bash
BACKUP_DIR=/srv/papa/backups /srv/papa/deploy/backup.sh
```

Per Cron (täglich 02:30 Uhr):

```cron
30 2 * * * BACKUP_DIR=/srv/papa/backups PGPASSWORD=... /srv/papa/deploy/backup.sh >> /var/log/papa-backup.log 2>&1
```

### Wiederherstellung

```bash
# Datenbank (Custom-Format):
pg_restore -U papa -h 127.0.0.1 -d papa --clean --if-exists backups/db-YYYYMMDD-HHMMSS.dump
# Medien:
tar -xzf backups/media-YYYYMMDD-HHMMSS.tar.gz -C /srv/papa
```

Die Wiederherstellung nach einem frischen Aufsetzen wurde mit einem Test-Dump geprüft; DB-Dump
und Medien-Archiv sollten stets aus demselben Backuplauf stammen.

## 5. Updates einspielen

```bash
cd /srv/papa
git pull
uv sync --no-dev
uv run python manage.py migrate
uv run python manage.py collectstatic --noinput
sudo systemctl restart papa
```

Ändern sich statische Dateien, aktualisiert sich der Service-Worker-Cache automatisch
(die Cache-Version leitet sich aus den gehashten Assets ab); Benutzer erhalten ein
Update-Banner.
