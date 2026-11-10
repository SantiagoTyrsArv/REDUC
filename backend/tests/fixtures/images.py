"""Synthetic JPEGs for tests: plain photos, photos with EXIF GPS and equirectangular panoramas."""

import io
from datetime import UTC, datetime

import numpy as np
from PIL import ExifTags, Image

from reduc.core.providers.images.base import ImageMeta

#: Colour of the panorama in the direction of each view (ahead, right, behind, left).
PANORAMA_COLOURS = {"front": (255, 0, 0), "right": (0, 255, 0), "back": (0, 0, 255), "left": (255, 255, 0)}


def jpeg(width: int = 64, height: int = 48, colour: tuple[int, int, int] = (120, 130, 140)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def _dms(value: float) -> tuple[float, float, float]:
    value = abs(value)
    degrees = int(value)
    minutes = int((value - degrees) * 60)
    seconds = round((value - degrees - minutes / 60) * 3600, 4)
    return (float(degrees), float(minutes), seconds)


def jpeg_with_gps(
    lon: float | None = -74.0651,
    lat: float | None = 4.6012,
    heading: float | None = 135.0,
    taken: str | None = "2026:03:14 10:30:00",
    orientation: int | None = None,
    focal_35mm: int | None = 26,
    size: tuple[int, int] = (80, 60),
    extra_tags: bool = False,
) -> bytes:
    """A JPEG whose EXIF carries position, heading and date like a phone photo."""
    image = Image.new("RGB", size, (90, 110, 130))
    exif = Image.Exif()
    if orientation is not None:
        exif[ExifTags.Base.Orientation] = orientation
    if extra_tags:
        exif[ExifTags.Base.Make] = "FabricanteSecreto"
        exif[ExifTags.Base.Artist] = "Nombre De La Persona"
    detail = exif.get_ifd(ExifTags.IFD.Exif)
    if taken is not None:
        detail[ExifTags.Base.DateTimeOriginal] = taken
    if focal_35mm is not None:
        detail[ExifTags.Base.FocalLengthIn35mmFilm] = focal_35mm
    if extra_tags:
        detail[ExifTags.Base.BodySerialNumber] = "SERIE-123456"
    if lon is not None and lat is not None:
        gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
        gps[ExifTags.GPS.GPSLatitudeRef] = "N" if lat >= 0 else "S"
        gps[ExifTags.GPS.GPSLatitude] = _dms(lat)
        gps[ExifTags.GPS.GPSLongitudeRef] = "E" if lon >= 0 else "W"
        gps[ExifTags.GPS.GPSLongitude] = _dms(lon)
        if heading is not None:
            gps[ExifTags.GPS.GPSImgDirectionRef] = "T"
            gps[ExifTags.GPS.GPSImgDirection] = heading
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def panorama(width: int = 400, height: int = 200) -> bytes:
    """Equirectangular image with one flat colour per quadrant of the horizon, centred on each view."""
    pixels = np.zeros((height, width, 3), dtype=np.uint8)
    quarter = width // 4
    # The centre column looks ahead; columns wrap around at ±180°.
    for index, name in enumerate(("back", "left", "front", "right")):
        start = (index * quarter - quarter // 2) % width
        columns = [(start + offset) % width for offset in range(quarter)]
        pixels[:, columns] = PANORAMA_COLOURS[name]
    buffer = io.BytesIO()
    Image.fromarray(pixels).save(buffer, format="PNG")
    return buffer.getvalue()


def meta(
    external_id: str,
    lon: float = 0.001,
    lat: float = 0.001,
    heading: float | None = 90.0,
    captured: datetime | None = None,
    provider: str = "upload",
    is_panorama: bool = False,
    license: str = "own",
) -> ImageMeta:
    return ImageMeta(
        provider=provider,
        external_id=external_id,
        captured_at=captured or datetime(2026, 1, 1, tzinfo=UTC),
        lon=lon,
        lat=lat,
        heading_deg=heading,
        width_px=64,
        height_px=48,
        license=license,
        attribution="Equipo REDUC",
        is_panorama=is_panorama,
    )
