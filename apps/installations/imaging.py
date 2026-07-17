"""Bildverarbeitung für Installationsfotos.

Jedes hochgeladene Bild wird validiert und neu kodiert: ein Original (auf Bildschirmgröße
begrenzt) und ein Thumbnail, beide als JPEG. Das Re-Encoding entfernt eingebettete Metadaten,
korrigiert die Ausrichtung anhand der EXIF-Daten und begrenzt die Dateigröße.
"""

from __future__ import annotations

import io

from PIL import Image, ImageOps

# Schutz vor „Decompression Bombs“: Bilder mit absurd vielen Pixeln werden abgelehnt.
Image.MAX_IMAGE_PIXELS = 60_000_000

#: Maximale Kantenlänge des gespeicherten Originals (Pixel).
MAX_ORIGINAL_PX = 2560
#: Maximale Kantenlänge des Thumbnails (Pixel).
THUMBNAIL_PX = 400
#: JPEG-Qualität für Original und Thumbnail.
JPEG_QUALITY = 85


class InvalidImageError(ValueError):
    """Wird geworfen, wenn hochgeladene Daten kein verarbeitbares Bild sind."""


def process_image(data: bytes) -> tuple[bytes, bytes]:
    """Validiert und re-kodiert ein Bild.

    :returns: Tupel ``(original_jpeg, thumbnail_jpeg)`` als Bytes.
    :raises InvalidImageError: bei ungültigen oder zu großen Bildern.
    """
    # 1. Integritätsprüfung (verify() macht das Bildobjekt danach unbrauchbar).
    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
    except Exception as exc:
        raise InvalidImageError("Die Datei ist kein gültiges Bild.") from exc

    # 2. Erneut öffnen, Ausrichtung korrigieren, in RGB wandeln.
    try:
        image: Image.Image = Image.open(io.BytesIO(data))
        image = ImageOps.exif_transpose(image)
        image = image.convert("RGB")
    except Exception as exc:
        raise InvalidImageError("Das Bild konnte nicht verarbeitet werden.") from exc

    original = _encode(_fit(image, MAX_ORIGINAL_PX))
    thumbnail = _encode(_fit(image, THUMBNAIL_PX))
    return original, thumbnail


def _fit(image: Image.Image, max_px: int) -> Image.Image:
    """Skaliert das Bild proportional, sodass keine Kante ``max_px`` überschreitet."""
    copy = image.copy()
    copy.thumbnail((max_px, max_px), Image.Resampling.LANCZOS)
    return copy


def _encode(image: Image.Image) -> bytes:
    """Kodiert ein Bild als optimiertes JPEG."""
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return buffer.getvalue()
