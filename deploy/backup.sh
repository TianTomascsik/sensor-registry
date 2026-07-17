#!/bin/sh
# Konsistentes Backup von Datenbank und Medienverzeichnis.
#
# Aufruf (z. B. per Cron):
#   BACKUP_DIR=/srv/papa/backups /srv/papa/deploy/backup.sh
#
# Authentifizierung für pg_dump über ~/.pgpass oder die Umgebungsvariable PGPASSWORD.
set -e

BACKUP_DIR="${BACKUP_DIR:-/srv/papa/backups}"
MEDIA_DIR="${MEDIA_DIR:-/srv/papa/media}"
DB_NAME="${DB_NAME:-papa}"
DB_USER="${DB_USER:-papa}"
DB_HOST="${DB_HOST:-127.0.0.1}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

# 1. Datenbank (komprimiertes Custom-Format, für pg_restore geeignet).
pg_dump -U "$DB_USER" -h "$DB_HOST" -Fc "$DB_NAME" > "$BACKUP_DIR/db-$STAMP.dump"

# 2. Medien (Fotos). Zusammen mit dem DB-Dump ergibt das einen konsistenten Stand.
if [ -d "$MEDIA_DIR" ]; then
    tar -czf "$BACKUP_DIR/media-$STAMP.tar.gz" -C "$(dirname "$MEDIA_DIR")" "$(basename "$MEDIA_DIR")"
fi

# 3. Alte Backups entfernen.
find "$BACKUP_DIR" -name 'db-*.dump' -mtime "+$RETENTION_DAYS" -delete
find "$BACKUP_DIR" -name 'media-*.tar.gz' -mtime "+$RETENTION_DAYS" -delete

echo "Backup erstellt (Stand $STAMP) in $BACKUP_DIR"
