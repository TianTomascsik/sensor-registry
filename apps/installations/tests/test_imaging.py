"""Tests der Bildpipeline."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from apps.installations.imaging import (
    MAX_ORIGINAL_PX,
    THUMBNAIL_PX,
    InvalidImageError,
    process_image,
)


def _image_bytes(size: tuple[int, int], fmt: str = "JPEG") -> bytes:
    image = Image.new("RGB", size, (120, 160, 200))
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def _dimensions(data: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as image:
        return image.size


def test_process_image_begrenzt_groesse_und_erzeugt_thumbnail() -> None:
    original, thumbnail = process_image(_image_bytes((4000, 3000)))

    ow, oh = _dimensions(original)
    assert max(ow, oh) == MAX_ORIGINAL_PX
    tw, th = _dimensions(thumbnail)
    assert max(tw, th) == THUMBNAIL_PX


def test_process_image_akzeptiert_png_und_liefert_jpeg() -> None:
    original, thumbnail = process_image(_image_bytes((800, 600), fmt="PNG"))
    with Image.open(io.BytesIO(original)) as image:
        assert image.format == "JPEG"
    with Image.open(io.BytesIO(thumbnail)) as image:
        assert image.format == "JPEG"


def test_process_image_lehnt_ungueltige_daten_ab() -> None:
    with pytest.raises(InvalidImageError):
        process_image(b"das ist kein bild")
