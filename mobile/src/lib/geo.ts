// Pure geometry over [lon, lat] pairs. Accurate enough at walking scale.
export type LonLat = [number, number];
export type Bounds = [west: number, south: number, east: number, north: number];

const EARTH_RADIUS_M = 6_371_008.8;
const toRad = (degrees: number): number => (degrees * Math.PI) / 180;

export function haversineM(a: LonLat, b: LonLat): number {
  const dLat = toRad(b[1] - a[1]);
  const dLon = toRad(b[0] - a[0]);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a[1])) * Math.cos(toRad(b[1])) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(Math.min(1, h)));
}

export function lineLengthM(coords: readonly LonLat[]): number {
  let total = 0;
  for (let i = 1; i < coords.length; i += 1) {
    total += haversineM(coords[i - 1]!, coords[i]!);
  }
  return total;
}

export interface Projection {
  /** Closest point on the line. */
  point: LonLat;
  /** Meters travelled along the line up to that point. */
  distanceAlongM: number;
  /** Meters between the given position and the line. */
  offsetM: number;
}

/** Project a position onto a polyline using a local equirectangular approximation. */
export function projectOnLine(coords: readonly LonLat[], position: LonLat): Projection | null {
  if (coords.length === 0) {
    return null;
  }
  if (coords.length === 1) {
    return { point: coords[0]!, distanceAlongM: 0, offsetM: haversineM(coords[0]!, position) };
  }
  const scaleX = Math.cos(toRad(position[1]));
  let best: Projection | null = null;
  let walked = 0;
  for (let i = 1; i < coords.length; i += 1) {
    const a = coords[i - 1]!;
    const b = coords[i]!;
    const ax = (a[0] - position[0]) * scaleX;
    const ay = a[1] - position[1];
    const bx = (b[0] - position[0]) * scaleX;
    const by = b[1] - position[1];
    const dx = bx - ax;
    const dy = by - ay;
    const lengthSq = dx * dx + dy * dy;
    const t = lengthSq === 0 ? 0 : Math.max(0, Math.min(1, -(ax * dx + ay * dy) / lengthSq));
    const point: LonLat = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
    const segmentM = haversineM(a, b);
    const offsetM = haversineM(point, position);
    if (best === null || offsetM < best.offsetM) {
      best = { point, distanceAlongM: walked + segmentM * t, offsetM };
    }
    walked += segmentM;
  }
  return best;
}

/** Point located a given number of meters along a polyline (clamped to its ends). */
export function pointAlongLine(coords: readonly LonLat[], distanceM: number): LonLat | null {
  if (coords.length === 0) {
    return null;
  }
  let remaining = Math.max(0, distanceM);
  for (let i = 1; i < coords.length; i += 1) {
    const a = coords[i - 1]!;
    const b = coords[i]!;
    const segmentM = haversineM(a, b);
    if (remaining <= segmentM && segmentM > 0) {
      const t = remaining / segmentM;
      return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
    }
    remaining -= segmentM;
  }
  return coords[coords.length - 1]!;
}

function ringContains(ring: readonly (readonly number[])[], point: LonLat): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i, i += 1) {
    const xi = ring[i]![0]!;
    const yi = ring[i]![1]!;
    const xj = ring[j]![0]!;
    const yj = ring[j]![1]!;
    if (yi > point[1] !== yj > point[1] && point[0] < ((xj - xi) * (point[1] - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

/** Whether a point is inside a GeoJSON Polygon or MultiPolygon (holes respected). */
export function geometryContains(geometry: unknown, point: LonLat): boolean {
  const shape = geometry as { type?: string; coordinates?: unknown };
  const polygons =
    shape.type === "Polygon"
      ? [shape.coordinates as number[][][]]
      : shape.type === "MultiPolygon"
        ? (shape.coordinates as number[][][][])
        : [];
  return polygons.some((polygon) => {
    const [outer, ...holes] = polygon;
    return outer !== undefined && ringContains(outer, point) && !holes.some((hole) => ringContains(hole, point));
  });
}

export function boundsOf(coords: readonly LonLat[]): Bounds | null {
  if (coords.length === 0) {
    return null;
  }
  let west = Infinity;
  let south = Infinity;
  let east = -Infinity;
  let north = -Infinity;
  for (const [lon, lat] of coords) {
    west = Math.min(west, lon);
    east = Math.max(east, lon);
    south = Math.min(south, lat);
    north = Math.max(north, lat);
  }
  // A degenerate box cannot be fitted by the map camera.
  const pad = west === east && south === north ? 0.0005 : 0;
  return [west - pad, south - pad, east + pad, north + pad];
}

export function boundsCenter(bounds: Bounds): LonLat {
  return [(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2];
}

/** Round a coordinate to a ~5 m grid so nearby requests share one cache entry. */
export function roundToGrid(point: LonLat): LonLat {
  const step = 0.00005;
  return [Math.round(point[0] / step) * step, Math.round(point[1] / step) * step];
}
