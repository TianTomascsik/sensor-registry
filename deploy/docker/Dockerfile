# Multi-Stage-Image für die Sensor-Dokumentation.
# Build-Kontext ist das Projektwurzelverzeichnis:
#   docker build -f deploy/docker/Dockerfile -t papa .

# --- Stage 1: Abhängigkeiten mit uv installieren ---
FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app
# Zuerst nur die Lock-Dateien kopieren (nutzt den Layer-Cache).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# --- Stage 2: schlankes Laufzeit-Image ---
FROM python:3.13-slim AS runtime

# Laufzeitbibliotheken für WeasyPrint (PDF) und Standardschriften.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_ENV=prod \
    GUNICORN_BIND=0.0.0.0:8000 \
    PATH="/app/.venv/bin:$PATH"

# Nicht als root laufen.
RUN useradd --create-home --uid 10001 papa
WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY . /app

# Verzeichnisse für Medien und statische Dateien dem App-Benutzer übergeben.
RUN mkdir -p /app/media /app/staticfiles && chown -R papa:papa /app/media /app/staticfiles
USER papa

EXPOSE 8000
ENTRYPOINT ["/app/deploy/docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "-c", "deploy/gunicorn.conf.py"]
