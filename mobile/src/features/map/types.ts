import type { StyleProp, ViewStyle } from "react-native";

import type { Bounds, LonLat } from "../../lib/geo";
import type { RouteStatus } from "../../theme";

export interface MapRouteSegment {
  coordinates: LonLat[];
  status: RouteStatus;
}

export interface MapRoute {
  id: string;
  coordinates: LonLat[];
  selected: boolean;
  /** Only needed for the selected route: it is drawn with per-segment status styling. */
  segments?: MapRouteSegment[];
}

export type MarkerKind = "origin" | "destination" | "position";

export interface MapMarker {
  id: string;
  kind: MarkerKind;
  location: LonLat;
}

/** Camera request. Change `key` to repeat the same move. */
export type MapFocus =
  | { kind: "bounds"; bounds: Bounds; key: string }
  | { kind: "center"; center: LonLat; zoom?: number; key: string };

export interface MapCanvasProps {
  /** Bounding box shown before any focus request, normally the active region. */
  initialBounds: Bounds | null;
  /** Version of the published map; changing it refreshes the vector tiles. */
  mapVersion: number | null;
  showAccessibility: boolean;
  routes?: MapRoute[];
  markers?: MapMarker[];
  focus?: MapFocus | null;
  onPress?: (location: LonLat) => void;
  onBarrierPress?: (barrierId: string) => void;
  accessibilityLabel: string;
  style?: StyleProp<ViewStyle>;
}
