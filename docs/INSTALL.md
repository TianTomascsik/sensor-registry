# Installation

Diese Anleitung beschreibt die Installation der Anwendung. Sie ist **vollständig ohne
Docker** möglich; die Docker-Variante wird zusätzlich als Option beschrieben.

Der aktuelle Stand ist **Phase 1**. Reverse-Proxy-Härtung, geschützte Medienauslieferung,
systemd-Dienste und die vollständige Produktionskonfiguration werden in Phase 8 ergänzt;
die hier beschriebenen Schritte reichen für einen lauffähigen Betrieb des aktuellen Stands.

---

## 1. Entwicklung (lokal)

### Voraussetzungen

- `uv` (installiert Python 3.13 automatisch): <https://docs.astral.sh/uv/>
- PostgreSQL 16 – entweder lokal installiert oder über das mitgelieferte Docker-Compose

### Schritte

```bash
uv sync
cp .env.example .env
docker compose -f deploy/docker/docker-compose.dev.yml up -d   # oder lokale PostgreSQL nutzen
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

Wird eine bereits vorhandene PostgreSQL genutzt, ist in der `.env` lediglich `DATABASE_URL`
auf die eigene Datenbank anzupassen.

---

## 2. Produktion unter Ubuntu LTS – ohne Docker

### 2.1 Systempakete

```bash
sudo apt update
sudo apt install -y python3.13 python3.13-venv git postgresql nginx \
  libpq-dev build-essential
# WeasyPrint-Systemabhängigkeiten (PDF-Export, ab Phase 7 genutzt – jetzt schadlos installierbar):
sudo apt install -y libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf-2.0-0
```

> Steht Python 3.13 im Ubuntu-Repository (noch) nicht bereit, kann `uv` es bereitstellen:
> `curl -LsSf https://astral.sh/uv/install.sh | sh` und danach `uv python install 3.13`.

### 2.2 Datenbank anlegen

```bash
sudo -u postgres psql <<'SQL'
CREATE USER papa WITH PASSWORD 'BITTE_SICHERES_PASSWORT';
CREATE DATABASE papa OWNER papa;
SQL
```

### 2.3 Anwendung bereitstellen

```bash
sudo mkdir -p /srv/papa
sudo chown "$USER" /srv/papa
git clone <REPOSITORY-URL> /srv/papa
cd /srv/papa

# Abhängigkeiten installieren – Variante A (empfohlen): uv
uv sync --no-dev

# Variante B ohne uv (reines venv + pip):
#   python3.13 -m venv .venv
#   . .venv/bin/activate
#   pip install -r requirements.txt
```

### 2.4 Konfiguration

```bash
cp .env.example .env
```

In der `.env` mindestens setzen:

```ini
DJANGO_ENV=prod
DJANGO_SECRET_KEY=<mit 'python -c "import secrets; print(secrets.token_urlsafe(64))"' erzeugen>
DJANGO_ALLOWED_HOSTS=app.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://app.example.com
DATABASE_URL=postgres://papa:BITTE_SICHERES_PASSWORT@127.0.0.1:5432/papa
DJANGO_SECURE_SSL=1
```

### 2.5 Datenbank migrieren, statische Dateien sammeln, Superadmin anlegen

```bash
export DJANGO_ENV=prod
uv run python manage.py migrate
uv run python manage.py collectstatic --noinput
uv run python manage.py createsuperuser
```

### 2.6 Anwendungsserver starten (Gunicorn)

```bash
uv run gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 3
```

Für den dauerhaften Betrieb wird dieser Prozess in Phase 8 über einen systemd-Dienst
verwaltet. Für einen ersten Produktionstest genügt der obige Aufruf (z. B. in `tmux`).

### 2.7 Nginx als Reverse Proxy (Grundkonfiguration)

Minimalkonfiguration, die statische Dateien direkt ausliefert und die Anwendung
weiterreicht (`/etc/nginx/sites-available/papa`):

```nginx
server {
    listen 80;
    server_name app.example.com;

    location /static/ {
        alias /srv/papa/staticfiles/;
        access_log off;
        expires 30d;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/papa /etc/nginx/sites-enabled/papa
sudo nginx -t && sudo systemctl reload nginx
```

TLS (HTTPS) wird typischerweise über Certbot/Let's Encrypt ergänzt. Die vollständige,
gehärtete Nginx-Konfiguration (Security-Header, geschützte Medien via `X-Accel-Redirect`)
folgt in Phase 8.

---

## 3. Produktion mit Docker (optional)

Ein vollständiges Produktions-Compose-Setup (Anwendung, PostgreSQL, Nginx) folgt in
Phase 8. Für die Entwicklung stellt bereits jetzt
`deploy/docker/docker-compose.dev.yml` eine PostgreSQL-Instanz bereit:

```bash
docker compose -f deploy/docker/docker-compose.dev.yml up -d
```

---

## 4. Datenbank-Backup (Grundlage)

```bash
# Sicherung
pg_dump -U papa -h 127.0.0.1 papa > backup_$(date +%Y%m%d).sql

# Wiederherstellung
psql -U papa -h 127.0.0.1 papa < backup_YYYYMMDD.sql
```

Sobald ab Phase 4 Fotos gespeichert werden, muss zusätzlich das Verzeichnis `media/`
konsistent mit dem Datenbank-Dump gesichert werden. Die vollständige Backup-/Restore-Prozedur
wird in Phase 8 dokumentiert und getestet.
