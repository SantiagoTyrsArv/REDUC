// One definition of the map layers for the native and web renderers (docs/07 §4).
// Status is encoded by colour AND line pattern: solid = accessible, dashed = caution,
// dotted = inaccessible, thin grey = no data.
import type { Palette } from "../../theme";

export interface LayerDef {
  id: string;
  type: "line" | "circle";
  "source-layer"?: string;
  filter?: unknown[];
  paint: Record<string, unknown>;
  layout?: Record<string, unknown>;
}

export const EDGE_SOURCE = "reduc-edges";
export const BARRIER_SOURCE = "reduc-barriers";
export const ALT_ROUTES_SOURCE = "reduc-routes-alt";
export const ROUTE_SOURCE = "reduc-route";
export const MARKER_SOURCE = "reduc-markers";

const STATUS_PATTERNS = {
  accessible: null,
  caution: [2, 1.5],
  inaccessible: [0.1, 2],
} as const;

const statusIs = (status: string): unknown[] => ["==", ["get", "status"], status];

export function edgeLayers(colors: Palette): LayerDef[] {
  const line = (status: "accessible" | "caution" | "inaccessible"): LayerDef => ({
    id: `reduc-edge-${status}`,
    type: "line",
    "source-layer": "edge_accessibility",
    filter: statusIs(status),
    layout: { "line-cap": "round", "line-join": "round" },
    paint: {
      "line-color": colors[status],
      "line-width": 4,
      ...(STATUS_PATTERNS[status] ? { "line-dasharray": STATUS_PATTERNS[status] } : {}),
    },
  });
  return [
    {
      id: "reduc-edge-unknown",
      type: "line",
      "source-layer": "edge_accessibility",
      filter: statusIs("unknown"),
      paint: { "line-color": colors.unknown, "line-width": 1.5 },
    },
    line("accessible"),
    line("caution"),
    line("inaccessible"),
  ];
}

/** Colour per barrier family; the legend spells out the same grouping in words. */
export const BARRIER_COLORS = {
  stairs: "#7b1fa2",
  curb: "#c2410c",
  obstacle: "#0f6cbd",
  surface: "#5f6368",
} as const;

export function barrierLayers(colors: Palette): LayerDef[] {
  return [
    {
      id: "reduc-barrier",
      type: "circle",
      "source-layer": "barrier",
      paint: {
        "circle-radius": 7,
        "circle-color": [
          "match",
          ["get", "class"],
          ["stairs", "single_step"],
          BARRIER_COLORS.stairs,
          "curb_no_ramp",
          BARRIER_COLORS.curb,
          "obstacle",
          BARRIER_COLORS.obstacle,
          BARRIER_COLORS.surface,
        ],
        "circle-stroke-color": colors.background,
        // Verified barriers carry a visibly thicker border.
        "circle-stroke-width": ["match", ["get", "verification_status"], ["confirmed", "manual"], 4, 1.5],
      },
    },
  ];
}

export function altRouteLayers(colors: Palette): LayerDef[] {
  return [
    {
      id: "reduc-route-alt",
      type: "line",
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": colors.unknown, "line-width": 5, "line-opacity": 0.7 },
    },
  ];
}

export function routeLayers(colors: Palette): LayerDef[] {
  const segment = (status: "accessible" | "caution" | "inaccessible"): LayerDef => ({
    id: `reduc-route-${status}`,
    type: "line",
    filter: statusIs(status),
    layout: { "line-cap": "round", "line-join": "round" },
    paint: {
      "line-color": colors[status],
      "line-width": 6,
      ...(STATUS_PATTERNS[status] ? { "line-dasharray": STATUS_PATTERNS[status] } : {}),
    },
  });
  return [
    {
      id: "reduc-route-casing",
      type: "line",
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": colors.background, "line-width": 11 },
    },
    segment("accessible"),
    segment("caution"),
    segment("inaccessible"),
  ];
}

export function markerLayers(colors: Palette): LayerDef[] {
  return [
    {
      id: "reduc-marker",
      type: "circle",
      paint: {
        "circle-radius": ["match", ["get", "kind"], "position", 8, 10],
        "circle-color": ["match", ["get", "kind"], "origin", colors.accessible, "destination", colors.danger, colors.primary],
        "circle-stroke-color": colors.background,
        "circle-stroke-width": 3,
      },
    },
  ];
}
