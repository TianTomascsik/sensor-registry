"""Test-Konfiguration.

Erbt von der Entwicklungskonfiguration und ergänzt ausschließlich die Test-Support-App
(:mod:`apps.testsupport`) mit Hilfsmodellen. Diese App ist bewusst nicht Teil von ``dev``
oder ``prod``, damit ihre Testtabellen niemals in echten Datenbanken landen.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from .dev import *  # noqa: F403
from .dev import INSTALLED_APPS

INSTALLED_APPS = [*INSTALLED_APPS, "apps.testsupport"]

# Hochgeladene Testdateien (Fotos) in ein temporäres Verzeichnis schreiben, damit das echte
# media/-Verzeichnis unberührt bleibt.
MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="papa-test-media-"))
