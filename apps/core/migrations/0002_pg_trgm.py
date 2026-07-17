"""Aktiviert die PostgreSQL-Erweiterung ``pg_trgm`` für die Teilstring-Suche.

``pg_trgm`` ist ab PostgreSQL 13 eine „trusted extension“ und kann daher auch vom
Datenbank-Eigentümer (ohne Superuser-Rechte) angelegt werden.
"""
from __future__ import annotations

from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        TrigramExtension(),
    ]
