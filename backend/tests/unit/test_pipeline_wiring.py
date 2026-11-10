"""Region config → pipeline dependencies, without network (T-22)."""

import shutil
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.osm.sample import EXPECTED_EDGES

from reduc.core.db.models import Region
from reduc.core.pipeline.stages.import_osm import StageConfigurationError
from reduc.core.pipeline.wiring import build_deps
from reduc.core.providers.elevation.base import ConstantElevation
from reduc.core.providers.osm.graph import build_graph
from reduc.core.storage import InMemoryStorage
from reduc.settings import Settings

FIXTURE = Path(__file__).parents[1] / "fixtures" / "osm" / "sample.osm.pbf"
BBOX = (-1.0, -1.0, 1.0, 1.0)


def region(config: dict[str, Any]) -> Region:
    return Region(slug="x", name="x", utm_srid=32631, config=config)


def test_osm_file_source_reads_from_the_data_directory(tmp_path: Path) -> None:
    shutil.copy(FIXTURE, tmp_path / "campus.osm.pbf")
    deps = build_deps(Settings(data_dir=str(tmp_path)), None)
    assert deps.osm_source is not None

    data = deps.osm_source(region({"osm": {"source": "file", "path": "campus.osm.pbf"}}), BBOX)

    assert len(build_graph(data).edges) == EXPECTED_EDGES


@pytest.mark.parametrize("path", ["../secreto.pbf", "/etc/passwd", "no-existe.osm.pbf", ""])
def test_file_paths_cannot_leave_the_data_directory(tmp_path: Path, path: str) -> None:
    (tmp_path.parent / "secreto.pbf").write_bytes(b"x")
    deps = build_deps(Settings(data_dir=str(tmp_path)), None)
    assert deps.osm_source is not None

    with pytest.raises(StageConfigurationError):
        deps.osm_source(region({"osm": {"source": "file", "path": path}}), BBOX)


def test_files_in_object_storage_and_unknown_sources(tmp_path: Path) -> None:
    storage = InMemoryStorage()
    storage.put("osm/campus.osm.pbf", FIXTURE.read_bytes(), "application/octet-stream")
    deps = build_deps(Settings(data_dir=str(tmp_path)), storage)
    assert deps.osm_source is not None and deps.elevation_source is not None

    data = deps.osm_source(region({"osm": {"source": "file", "path": "s3://reduc/osm/campus.osm.pbf"}}), BBOX)

    assert len(build_graph(data).edges) == EXPECTED_EDGES
    with pytest.raises(StageConfigurationError, match="almacenamiento"):
        build_deps(Settings(data_dir=str(tmp_path)), None).osm_source(  # type: ignore[misc]
            region({"osm": {"source": "file", "path": "s3://reduc/osm/campus.osm.pbf"}}), BBOX
        )
    with pytest.raises(StageConfigurationError, match="no soportada"):
        deps.osm_source(region({"osm": {"source": "ftp"}}), BBOX)
    assert deps.elevation_source(region({})) is None
    flat = deps.elevation_source(region({"elevation": {"source": "flat", "elevation_m": 2600}}))
    assert isinstance(flat, ConstantElevation) and flat.elevation_m == 2600.0
    with pytest.raises(StageConfigurationError, match="no soportada"):
        deps.elevation_source(region({"elevation": {"source": "magic"}}))
