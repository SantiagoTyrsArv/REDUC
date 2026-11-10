// GeoJSON builders shared by both map renderers.
import type { MapMarker, MapRoute } from "./types";

type FeatureCollection = GeoJSON.FeatureCollection;

export function altRoutesData(routes: readonly MapRoute[]): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: routes
      .filter((route) => !route.selected && route.coordinates.length > 1)
      .map((route) => ({
        type: "Feature",
        properties: { id: route.id },
        geometry: { type: "LineString", coordinates: route.coordinates },
      })),
  };
}

export function selectedRouteData(routes: readonly MapRoute[]): FeatureCollection {
  const selected = routes.find((route) => route.selected);
  if (!selected) {
    return { type: "FeatureCollection", features: [] };
  }
  const segments = selected.segments ?? [{ coordinates: selected.coordinates, status: "accessible" as const }];
  return {
    type: "FeatureCollection",
    features: segments
      .filter((segment) => segment.coordinates.length > 1)
      .map((segment, index) => ({
        type: "Feature",
        properties: { index, status: segment.status === "unknown" ? "caution" : segment.status },
        geometry: { type: "LineString", coordinates: segment.coordinates },
      })),
  };
}

export function markersData(markers: readonly MapMarker[]): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: markers.map((marker) => ({
      type: "Feature",
      properties: { id: marker.id, kind: marker.kind },
      geometry: { type: "Point", coordinates: marker.location },
    })),
  };
}

export function tileUrl(tilesUrl: string, source: "edge_accessibility" | "barrier", mapVersion: number | null): string {
  // The version only busts caches when a new map is published; Martin ignores the parameter.
  return `${tilesUrl}/${source}/{z}/{x}/{y}${mapVersion === null ? "" : `?v=${mapVersion}`}`;
}
