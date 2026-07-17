#!/bin/sh
# Wartet auf die Datenbank, wendet Migrationen an, sammelt statische Dateien und startet
# anschließend das übergebene Kommando (Gunicorn).
set -e

# Auf die Datenbank warten (aus DATABASE_URL abgeleitet).
python - <<'PY'
import os
import socket
import time
import urllib.parse

parsed = urllib.parse.urlparse(os.environ.get("DATABASE_URL", ""))
host = parsed.hostname or "db"
port = parsed.port or 5432
for _ in range(60):
    try:
        with socket.create_connection((host, port), timeout=2):
            break
    except OSError:
        time.sleep(1)
else:
    raise SystemExit(f"Datenbank unter {host}:{port} nicht erreichbar.")
PY

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec "$@"
