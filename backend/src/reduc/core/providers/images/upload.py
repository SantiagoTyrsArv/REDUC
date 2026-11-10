"""Photos taken by the team (docs/05 §4): position, heading and date come from EXIF."""

import hashlib
import io
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from PIL import ExifTags, Image, UnidentifiedImageError

from reduc.core.providers.images.base import Boundary, ImageMeta, ImageRejectedError

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 80_000_000
ALLOWED_FORMATS = frozenset({"JPEG", "MPO"})
LICENSE = "own"
#: Phone photos are taken at about chest height.
UPLOAD_CAMERA_HEIGHT_M = 1.4
_GPS_IFD = 0x8825
_EXIF_IFD = 0x8769


@dataclass(frozen=True)
class ExifInfo:
    lon: float
    lat: float
    heading_deg: float | None
    captured_at: datetime | None
    width_px: int
    height_px: int
    fov_deg: float | None


def _degrees(value: Any, reference: Any) -> float:
    degrees, minutes, seconds = (float(part) for part in value)
    decimal = degrees + minutes / 60.0 + seconds / 3600.0
    return -decimal if str(reference).upper() in {"S", "W"} else decimal


def _captured_at(exif: Any, gps: dict[int, Any]) -> datetime | None:
    detail = exif.get_ifd(_EXIF_IFD)
    raw = detail.get(ExifTags.Base.DateTimeOriginal) or exif.get(ExifTags.Base.DateTime)
    if not raw:
        return None
    try:
        # EXIF local time has no zone; UTC is assumed, which is precise enough to order photos.
        return datetime.strptime(str(raw).strip("\x00 "), "%Y:%m:%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def _fov(exif: Any) -> float | None:
    """Horizontal field of view from the 35 mm equivalent focal length, when the camera wrote it."""
    import math

    focal = exif.get_ifd(_EXIF_IFD).get(ExifTags.Base.FocalLengthIn35mmFilm)
    try:
        focal_mm = float(focal)
    except (TypeError, ValueError):
        return None
    if focal_mm <= 0:
        return None
    return round(math.degrees(2.0 * math.atan(36.0 / (2.0 * focal_mm))), 1)


def read_exif(data: bytes) -> ExifInfo:
    """Validate an uploaded photo and extract what the pipeline needs. Raises ImageRejectedError."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageRejectedError("La foto supera los 20 MB")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in ALLOWED_FORMATS:
                raise ImageRejectedError("Solo se aceptan fotos JPEG")
            width, height = image.size
            if width * height > MAX_PIXELS:
                raise ImageRejectedError("La foto tiene demasiados píxeles")
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            exif = image.getexif()
            gps: dict[int, Any] = dict(exif.get_ifd(_GPS_IFD))
            # Phones store portrait photos rotated; orientations 5-8 swap width and height.
            if exif.get(ExifTags.Base.Orientation) in {5, 6, 7, 8}:
                width, height = height, width
            captured = _captured_at(exif, gps)
            fov = _fov(exif)
    except ImageRejectedError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as error:
        raise ImageRejectedError("El archivo no es una imagen JPEG válida") from error

    try:
        lat = _degrees(gps[ExifTags.GPS.GPSLatitude], gps.get(ExifTags.GPS.GPSLatitudeRef, "N"))
        lon = _degrees(gps[ExifTags.GPS.GPSLongitude], gps.get(ExifTags.GPS.GPSLongitudeRef, "E"))
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        raise ImageRejectedError("La foto no tiene posición GPS en sus metadatos EXIF") from error
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0) or (lat == 0.0 and lon == 0.0):
        raise ImageRejectedError("La posición GPS de la foto no es válida")
    heading: float | None = None
    try:
        direction = gps.get(ExifTags.GPS.GPSImgDirection)
        heading = None if direction is None else float(direction) % 360.0
    except (TypeError, ValueError, ZeroDivisionError):
        heading = None
    return ExifInfo(lon, lat, heading, captured, width, height, fov)


def upload_meta(data: bytes, heading_deg: float | None = None, now: datetime | None = None) -> ImageMeta:
    """Metadata of an uploaded photo. A heading typed by the uploader overrides the EXIF one."""
    info = read_exif(data)
    heading = info.heading_deg if heading_deg is None else float(heading_deg) % 360.0
    if heading is None:
        raise ImageRejectedError("La foto no indica hacia dónde mira la cámara; escribe el rumbo manualmente")
    return ImageMeta(
        provider="upload",
        # The same file uploaded twice is the same image.
        external_id=hashlib.sha256(data).hexdigest()[:32],
        captured_at=info.captured_at or now or datetime.now(UTC),
        lon=info.lon,
        lat=info.lat,
        heading_deg=heading,
        width_px=info.width_px,
        height_px=info.height_px,
        license=LICENSE,
        attribution=None,
        fov_deg=info.fov_deg,
        camera_height_m=UPLOAD_CAMERA_HEIGHT_M,
    )


class UploadProvider:
    """Uploads are pushed through the admin API, so there is nothing to list or download."""

    name = "upload"

    def list_images(self, boundary: Boundary, since: datetime | None) -> Iterator[ImageMeta]:
        return iter(())

    def fetch(self, meta: ImageMeta) -> bytes:
        raise LookupError("Uploaded images are already in storage")

    def can_store(self) -> bool:
        return True
