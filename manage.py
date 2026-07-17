#!/usr/bin/env python
"""Kommandozeilen-Einstiegspunkt für administrative Aufgaben."""

from __future__ import annotations

import os
import sys


def main() -> None:
    """Führt die von Django bereitgestellten Verwaltungsbefehle aus.

    Das zu ladende Settings-Modul wird aus der Umgebungsvariablen ``DJANGO_ENV``
    abgeleitet (``dev`` oder ``prod``); Standard ist ``dev``.
    """
    env = os.environ.get("DJANGO_ENV", "dev")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", f"config.settings.{env}")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover - nur bei fehlender Installation
        raise ImportError(
            "Django konnte nicht importiert werden. Ist die virtuelle Umgebung "
            "aktiviert und wurden die Abhängigkeiten installiert (uv sync)?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
