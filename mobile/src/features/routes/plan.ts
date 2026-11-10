// Pure helpers over the routes returned by POST /v1/routes.
import type { Route, RouteWarning } from "@reduc/api-client";

import type { LonLat } from "../../lib/geo";
import type { RouteStatus } from "../../theme";
import type { MapRoute } from "../map/types";

/** Worst status found along the route; shown next to the colour as text and shape. */
export function routeStatus(route: Route): RouteStatus {
  if (route.segments.some((segment) => segment.status === "inaccessible")) {
    return "inaccessible";
  }
  if (route.caution_segments > 0 || route.segments.some((segment) => segment.status === "caution")) {
    return "caution";
  }
  return "accessible";
}

/** Warnings of the whole route without repetitions, most severe first. */
export function uniqueWarnings(route: Route): RouteWarning[] {
  const seen = new Map<string, RouteWarning>();
  for (const segment of route.segments) {
    for (const warning of segment.warnings) {
      if (!seen.has(warning.message)) {
        seen.set(warning.message, warning);
      }
    }
  }
  return [...seen.values()].sort((a, b) => Number(b.severity === "major") - Number(a.severity === "major"));
}

export function toMapRoutes(routes: readonly Route[], selectedId: string | null): MapRoute[] {
  return routes.map((route) => {
    const selected = route.id === selectedId;
    return {
      id: route.id,
      coordinates: route.geometry.coordinates as LonLat[],
      selected,
      ...(selected
        ? {
            segments: route.segments.map((segment) => ({
              coordinates: segment.geometry.coordinates as LonLat[],
              status: segment.status,
            })),
          }
        : {}),
    };
  });
}
