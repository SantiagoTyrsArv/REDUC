"""Production dependencies of the pipeline, chosen by each region's `config` (docs/03 §3)."""

import tempfile
from pathlib import Path
from typing import Any

from reduc.core.db.models import Region
from reduc.core.pipeline.context import PipelineDeps
from reduc.core.pipeline.stages.import_osm import StageConfigurationError
from reduc.core.providers.elevation.base import ConstantElevation, ElevationSource
from reduc.core.providers.elevation.raster_file import RasterFileElevation
from reduc.core.providers.osm.graph import Bbox, OsmData
from reduc.core.providers.osm.overpass import DEFAULT_ENDPOINT, OverpassSource
from reduc.core.providers.osm.readers import read_osm_file
from reduc.core.storage import ObjectStorage
from reduc.settings import Settings


def _local_copy(location: str, storage: ObjectStorage | None, data_dir: Path, suffix: str) -> Path:
    """Resolve `s3://bucket/key` through object storage and anything else inside the data directory."""
    if location.startswith("s3://"):
        if storage is None:
            raise StageConfigurationError("El archivo está en S3 pero el almacenamiento no está configurado")
        key = location.removeprefix("s3://").split("/", 1)[-1]
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
            handle.write(storage.get(key))
            return Path(handle.name)
    # Region config is written by administrators, but it must still not reach arbitrary files.
    root = data_dir.resolve()
    path = (root / location).resolve()
    if not path.is_relative_to(root):
        raise StageConfigurationError("La ruta del archivo debe estar dentro del directorio de datos")
    if not path.is_file():
        raise StageConfigurationError(f"No existe el archivo de datos: {location}")
    return path


def build_deps(settings: Settings, storage: ObjectStorage | None) -> PipelineDeps:
    data_dir = Path(settings.data_dir)

    def osm_source(region: Region, bbox: Bbox) -> OsmData:
        config: dict[str, Any] = (region.config or {}).get("osm") or {}
        source = config.get("source", "overpass")
        if source == "overpass":
            return OverpassSource(endpoint=settings.overpass_endpoint or DEFAULT_ENDPOINT).fetch(bbox)
        if source == "file":
            return read_osm_file(_local_copy(str(config.get("path", "")), storage, data_dir, ".osm.pbf"))
        raise StageConfigurationError(f"Fuente OSM no soportada: {source}")

    def elevation_source(region: Region) -> ElevationSource | None:
        config: dict[str, Any] = (region.config or {}).get("elevation") or {}
        source = config.get("source")
        if source is None or source == "none":
            return None
        if source == "raster_file":
            return RasterFileElevation(_local_copy(str(config.get("path", "")), storage, data_dir, ".tif"))
        if source == "flat":
            return ConstantElevation(float(config.get("elevation_m", 0.0)))
        raise StageConfigurationError(f"Fuente de elevación no soportada: {source}")

    return PipelineDeps(osm_source=osm_source, elevation_source=elevation_source)
