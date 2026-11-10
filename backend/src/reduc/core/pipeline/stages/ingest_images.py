"""Stage 3: bring the images of every enabled source into `image` and object storage (docs/05 §4).

Images belong to the region, not to a map version: a later run only downloads what is new.
"""

import io
from datetime import UTC, datetime
from typing import Any

import structlog
from geoalchemy2.elements import WKTElement
from PIL import Image as PilImage
from sqlalchemy import select, text

from reduc.core.db.models import Image
from reduc.core.pipeline.context import BATCH_SIZE, StageContext, StageStats
from reduc.core.providers.images.base import ImageMeta, ImageProvider, dedupe
from reduc.core.providers.images.panorama import VIEW_FOV_DEG, split_panorama

DEFAULT_MAX_IMAGES = 20_000
#: Mapillary blurs faces and plates before publishing; uploads are blurred by `privacy.py` on arrival.
PRE_BLURRED_PROVIDERS = frozenset({"mapillary", "streetview"})

log = structlog.get_logger("reduc.pipeline.ingest")


def storage_key(region_id: Any, provider: str, external_id: str) -> str:
    safe = "".join(character if character.isalnum() or character in "-_" else "_" for character in external_id)
    return f"images/{region_id}/{provider}/{safe}.jpg"


def load_boundary(ctx: StageContext) -> Any:
    from shapely import wkb

    raw: Any = ctx.session.execute(
        text("SELECT ST_AsBinary(boundary) FROM region WHERE id = :id"), {"id": ctx.region.id}
    ).scalar_one()
    return wkb.loads(bytes(raw))


def _source_config(ctx: StageContext, provider: str) -> dict[str, Any]:
    for entry in (ctx.region.config or {}).get("image_sources") or []:
        if isinstance(entry, dict) and entry.get("provider") == provider:
            return entry
    return {}


def _since(config: dict[str, Any]) -> datetime | None:
    value = config.get("min_captured_at")
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _views(meta: ImageMeta, data: bytes) -> list[tuple[ImageMeta, bytes]]:
    """A panorama becomes four perspective images; everything downstream handles only those."""
    if not meta.is_panorama:
        return [(meta, data)]
    from dataclasses import replace

    heading = meta.heading_deg or 0.0
    return [
        (
            replace(
                meta,
                external_id=f"{meta.external_id}:{view.name}",
                heading_deg=(heading + view.offset_deg) % 360.0,
                fov_deg=VIEW_FOV_DEG,
                pitch_deg=0.0,
                width_px=view.size_px,
                height_px=view.size_px,
                is_panorama=False,
            ),
            view.jpeg,
        )
        for view in split_panorama(data)
    ]


def _ingest_provider(ctx: StageContext, provider: ImageProvider, boundary: Any) -> dict[str, int]:
    config = _source_config(ctx, provider.name)
    limit = int(config.get("max_images", DEFAULT_MAX_IMAGES))
    listed = dedupe(provider.list_images(boundary, _since(config)))
    # When there are more than the cap, the most recent ones describe the present best.
    candidates = sorted(listed, key=lambda meta: meta.captured_at, reverse=True)[:limit]
    existing = set(
        ctx.session.scalars(
            select(Image.external_id).where(Image.region_id == ctx.region.id, Image.provider == provider.name)
        )
    )
    new = [
        meta for meta in candidates if meta.external_id not in existing and f"{meta.external_id}:front" not in existing
    ]
    storage = ctx.deps.storage if provider.can_store() else None
    stats = {"listed": len(listed), "new": 0, "stored": 0, "failed": 0, "already_known": len(candidates) - len(new)}
    transient: dict[Any, bytes] = ctx.deps.extras.setdefault("transient_images", {})

    for start in range(0, len(new), BATCH_SIZE):
        for meta in new[start : start + BATCH_SIZE]:
            try:
                views = _views(meta, provider.fetch(meta))
            except Exception:
                # One broken download must not abort the stage; the image is retried on the next run.
                log.warning("image_fetch_failed", provider=provider.name, external_id=meta.external_id)
                stats["failed"] += 1
                continue
            for view, data in views:
                with PilImage.open(io.BytesIO(data)) as picture:
                    width, height = picture.size
                key = storage_key(ctx.region.id, provider.name, view.external_id) if storage is not None else None
                if storage is not None and key is not None:
                    storage.put(key, data, "image/jpeg")
                    stats["stored"] += 1
                row = Image(
                    region_id=ctx.region.id,
                    provider=provider.name,
                    external_id=view.external_id,
                    captured_at=view.captured_at,
                    geom=WKTElement(f"POINT({view.lon!r} {view.lat!r})", srid=4326),
                    heading_deg=view.heading_deg,
                    pitch_deg=view.pitch_deg,
                    fov_deg=view.fov_deg,
                    is_panorama=False,
                    camera_height_m=view.camera_height_m,
                    storage_key=key,
                    width_px=width,
                    height_px=height,
                    license=view.license,
                    attribution=view.attribution,
                    privacy_blurred=provider.name in PRE_BLURRED_PROVIDERS,
                    status="pending",
                )
                ctx.session.add(row)
                ctx.session.flush()
                if key is None:
                    # The licence forbids keeping a copy: the bytes only live for this run.
                    transient[row.id] = data
                stats["new"] += 1
        ctx.checkpoint(min(len(new), start + BATCH_SIZE), len(new))
    return stats


def run(ctx: StageContext) -> StageStats:
    providers = ctx.deps.image_providers(ctx.region) if ctx.deps.image_providers is not None else []
    boundary = load_boundary(ctx)
    by_provider = {provider.name: _ingest_provider(ctx, provider, boundary) for provider in providers}
    ctx.checkpoint(1, 1)
    return {
        "providers": by_provider,
        "new": sum(stats["new"] for stats in by_provider.values()),
        "failed": sum(stats["failed"] for stats in by_provider.values()),
    }
