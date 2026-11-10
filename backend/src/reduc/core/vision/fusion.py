"""Fuse geolocated detections into barriers (docs/05 §8). Pure logic in metric coordinates."""

import math
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from statistics import median
from typing import Any

NEGATIVE_EVIDENCE_FACTOR = 0.6
NEGATIVE_EVIDENCE_MIN_IMAGES = 3
TRANSFER_RADIUS_M = 3.0
OSM_CONFIDENCE = 0.7
MIN_IMAGE_QUALITY = 0.5


@dataclass(frozen=True)
class Observation:
    """One geolocated detection, in the UTM zone of its region."""

    id: str
    barrier_class: str
    x: float
    y: float
    score: float
    geo_error_m: float
    image_id: str
    image_quality: float = 1.0
    attributes: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FusedBarrier:
    barrier_class: str
    x: float
    y: float
    confidence: float
    n_observations: int
    observation_ids: tuple[str, ...]
    representative_id: str
    attributes: Mapping[str, Any]


@dataclass(frozen=True)
class KnownBarrier:
    """A barrier of an earlier state of the map whose human review must not be lost."""

    id: str
    barrier_class: str
    x: float
    y: float


def cluster(observations: Sequence[Observation], eps_m: float) -> list[list[Observation]]:
    """DBSCAN with `min_samples = 1` per class: connected components of the eps-neighbourhood graph."""
    by_class: dict[str, list[Observation]] = defaultdict(list)
    for observation in observations:
        by_class[observation.barrier_class].append(observation)

    clusters: list[list[Observation]] = []
    for barrier_class in sorted(by_class):
        items = sorted(by_class[barrier_class], key=lambda item: item.id)
        parent = list(range(len(items)))

        def find(index: int, parent: list[int] = parent) -> int:
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        # A uniform grid keeps the neighbour search linear for large regions.
        grid: dict[tuple[int, int], list[int]] = defaultdict(list)
        for index, item in enumerate(items):
            cell = (math.floor(item.x / eps_m), math.floor(item.y / eps_m))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for other in grid.get((cell[0] + dx, cell[1] + dy), ()):
                        if math.hypot(item.x - items[other].x, item.y - items[other].y) <= eps_m:
                            parent[find(index)] = find(other)
            grid[cell].append(index)

        groups: dict[int, list[Observation]] = defaultdict(list)
        for index, item in enumerate(items):
            groups[find(index)].append(item)
        clusters.extend(groups[root] for root in sorted(groups, key=lambda root: groups[root][0].id))
    return clusters


def aggregate_confidence(members: Sequence[Observation]) -> float:
    """`1 - Π(1 - score_i · w_i)` with `w_i` the image quality clamped to 0.5 to 1."""
    miss = 1.0
    for member in members:
        quality = min(1.0, max(MIN_IMAGE_QUALITY, member.image_quality))
        miss *= 1.0 - min(1.0, max(0.0, member.score)) * quality
    return 1.0 - miss


def _merge_attributes(members: Sequence[Observation], representative: Observation) -> dict[str, Any]:
    merged: dict[str, Any] = dict(representative.attributes)
    keys = {key for member in members for key in member.attributes}
    for key in keys:
        values = [member.attributes[key] for member in members if isinstance(member.attributes.get(key), int | float)]
        numeric = [float(value) for value in values if not isinstance(value, bool)]
        if not numeric:
            continue
        # Counts stay integers; heights and widths take the conservative median.
        value = median(numeric)
        merged[key] = round(value) if key.endswith("_count") else round(value, 2)
    return merged


def fuse(
    observations: Sequence[Observation],
    eps_m: float,
    images_covering: Callable[[float, float], int] | None = None,
) -> list[FusedBarrier]:
    """Group observations and compute position, confidence and attributes of each barrier.

    `images_covering(x, y)` returns how many images photographed that spot; it enables the
    negative-evidence rule (seen by only one of three or more images → confidence times 0.6).
    """
    fused: list[FusedBarrier] = []
    for members in cluster(observations, eps_m):
        weights = [member.score / max(member.geo_error_m, 0.1) ** 2 for member in members]
        total = sum(weights)
        if total <= 0.0:
            weights = [1.0] * len(members)
            total = float(len(members))
        x = sum(member.x * weight for member, weight in zip(members, weights, strict=True)) / total
        y = sum(member.y * weight for member, weight in zip(members, weights, strict=True)) / total

        confidence = aggregate_confidence(members)
        detecting_images = {member.image_id for member in members}
        if (
            images_covering is not None
            and len(detecting_images) == 1
            and images_covering(x, y) >= NEGATIVE_EVIDENCE_MIN_IMAGES
        ):
            confidence *= NEGATIVE_EVIDENCE_FACTOR

        representative = max(members, key=lambda member: (member.score, member.id))
        fused.append(
            FusedBarrier(
                barrier_class=members[0].barrier_class,
                x=x,
                y=y,
                confidence=round(min(1.0, confidence), 4),
                n_observations=len(members),
                observation_ids=tuple(member.id for member in members),
                representative_id=representative.id,
                attributes=_merge_attributes(members, representative),
            )
        )
    return fused


def match_known(
    barriers: Sequence[tuple[str, float, float]],
    known: Sequence[KnownBarrier],
    radius_m: float = TRANSFER_RADIUS_M,
) -> dict[int, str]:
    """Pair new barriers `(class, x, y)` with known ones of the same class within `radius_m`.

    Closest pairs win and every known barrier is used at most once. Returns
    `{index of the new barrier: id of the known barrier}`.
    """
    candidates: list[tuple[float, int, str]] = []
    for index, (barrier_class, x, y) in enumerate(barriers):
        for item in known:
            if item.barrier_class != barrier_class:
                continue
            distance = math.hypot(item.x - x, item.y - y)
            if distance <= radius_m:
                candidates.append((distance, index, item.id))
    matches: dict[int, str] = {}
    used: set[str] = set()
    for _, index, known_id in sorted(candidates):
        if index not in matches and known_id not in used:
            matches[index] = known_id
            used.add(known_id)
    return matches
