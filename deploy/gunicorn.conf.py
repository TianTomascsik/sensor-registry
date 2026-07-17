"""Gunicorn-Konfiguration für den Produktionsbetrieb.

Aufruf (systemd oder Docker):
    gunicorn config.wsgi:application -c deploy/gunicorn.conf.py
"""

from __future__ import annotations

import multiprocessing
import os

# Adresse: im Docker-Container an alle Interfaces, bei systemd nur lokal (Nginx davor).
bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:8000")

# Worker-Anzahl konservativ wählen (Bildverarbeitung/PDF sind CPU-intensiv).
_default_workers = min(max(multiprocessing.cpu_count() * 2 + 1, 3), 9)
workers = int(os.environ.get("GUNICORN_WORKERS", _default_workers))

# Zeitlimit etwas höher, damit Foto-Neukodierung und PDF-Erzeugung nicht abbrechen.
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "60"))
graceful_timeout = 30
keepalive = 5

# Worker-Heartbeat-Dateien im RAM (schneller, weniger Platten-I/O).
worker_tmp_dir = "/dev/shm"

# Logs auf stdout/stderr (systemd/Docker sammeln sie).
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOGLEVEL", "info")
