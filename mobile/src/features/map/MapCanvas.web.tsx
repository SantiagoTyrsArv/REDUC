// Web map renderer on MapLibre GL JS. Same props and layer definitions as the native one.
import "maplibre-gl/dist/maplibre-gl.css";

import maplibregl, { type GeoJSONSource, type LayerSpecification, type Map as GlMap } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";
import { StyleSheet, View } from "react-native";

import { config } from "../../lib/config";
import { useTheme } from "../../theme";
import { altRoutesData, markersData, selectedRouteData, tileUrl } from "./data";
import {
  ALT_ROUTES_SOURCE,
  BARRIER_SOURCE,
  EDGE_SOURCE,
  MARKER_SOURCE,
  ROUTE_SOURCE,
  altRouteLayers,
  barrierLayers,
  edgeLayers,
  markerLayers,
  routeLayers,
  type LayerDef,
} from "./layers";
import type { MapCanvasProps } from "./types";

const FIT_PADDING = 56;
const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

function addLayers(map: GlMap, source: string, defs: LayerDef[]): void {
  for (const def of defs) {
    if (!map.getLayer(def.id)) {
      map.addLayer({ ...def, source } as unknown as LayerSpecification);
    }
  }
}

export function MapCanvas({
  initialBounds,
  mapVersion,
  showAccessibility,
  routes = [],
  markers = [],
  focus = null,
  onPress,
  onBarrierPress,
  accessibilityLabel,
  style,
}: MapCanvasProps) {
  const { colors } = useTheme();
  const container = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<GlMap | null>(null);
  const [ready, setReady] = useState(false);
  // Handlers are read through refs so the map is not rebuilt when they change.
  const pressRef = useRef(onPress);
  const barrierPressRef = useRef(onBarrierPress);
  pressRef.current = onPress;
  barrierPressRef.current = onBarrierPress;

  // The map is created once per colour scheme and tile version.
  useEffect(() => {
    if (!container.current) {
      return undefined;
    }
    const map = new maplibregl.Map({
      container: container.current,
      style: config.mapStyleUrl,
      ...(initialBounds ? { bounds: initialBounds, fitBoundsOptions: { padding: FIT_PADDING } } : {}),
      attributionControl: { compact: true },
    });
    mapRef.current = map;

    map.on("load", () => {
      map.addSource(EDGE_SOURCE, {
        type: "vector",
        tiles: [tileUrl(config.tilesUrl, "edge_accessibility", mapVersion)],
        minzoom: 10,
        maxzoom: 18,
      });
      map.addSource(BARRIER_SOURCE, {
        type: "vector",
        tiles: [tileUrl(config.tilesUrl, "barrier", mapVersion)],
        minzoom: 10,
        maxzoom: 18,
      });
      map.addSource(ALT_ROUTES_SOURCE, { type: "geojson", data: EMPTY });
      map.addSource(ROUTE_SOURCE, { type: "geojson", data: EMPTY });
      map.addSource(MARKER_SOURCE, { type: "geojson", data: EMPTY });
      addLayers(map, EDGE_SOURCE, edgeLayers(colors));
      addLayers(map, ALT_ROUTES_SOURCE, altRouteLayers(colors));
      addLayers(map, ROUTE_SOURCE, routeLayers(colors));
      addLayers(map, BARRIER_SOURCE, barrierLayers(colors));
      addLayers(map, MARKER_SOURCE, markerLayers(colors));
      setReady(true);
    });

    map.on("click", (event) => {
      const barrier = map.getLayer("reduc-barrier")
        ? map.queryRenderedFeatures(
            [
              [event.point.x - 12, event.point.y - 12],
              [event.point.x + 12, event.point.y + 12],
            ],
            { layers: ["reduc-barrier"] },
          )[0]
        : undefined;
      const id = barrier?.properties?.id;
      if (typeof id === "string" && barrierPressRef.current) {
        barrierPressRef.current(id);
        return;
      }
      pressRef.current?.([event.lngLat.lng, event.lngLat.lat]);
    });
    map.on("mouseenter", "reduc-barrier", () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", "reduc-barrier", () => {
      map.getCanvas().style.cursor = "";
    });

    return () => {
      setReady(false);
      mapRef.current = null;
      map.remove();
    };
    // initialBounds only matters at creation time.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [colors, mapVersion]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) {
      return;
    }
    const visibility = showAccessibility ? "visible" : "none";
    for (const def of [...edgeLayers(colors), ...barrierLayers(colors)]) {
      if (map.getLayer(def.id)) {
        map.setLayoutProperty(def.id, "visibility", visibility);
      }
    }
  }, [ready, showAccessibility, colors]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) {
      return;
    }
    (map.getSource(ALT_ROUTES_SOURCE) as GeoJSONSource | undefined)?.setData(altRoutesData(routes));
    (map.getSource(ROUTE_SOURCE) as GeoJSONSource | undefined)?.setData(selectedRouteData(routes));
  }, [ready, routes]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) {
      return;
    }
    (map.getSource(MARKER_SOURCE) as GeoJSONSource | undefined)?.setData(markersData(markers));
  }, [ready, markers]);

  const focusKey = focus?.key ?? null;
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !focus) {
      return;
    }
    if (focus.kind === "bounds") {
      map.fitBounds(focus.bounds, { padding: FIT_PADDING, duration: 600, maxZoom: 18 });
    } else {
      map.easeTo({ center: focus.center, zoom: focus.zoom ?? 17, duration: 600 });
    }
    // The key alone decides when to move the camera.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, focusKey]);

  return (
    <View style={[style ?? styles.fill, styles.clip]}>
      <div
        ref={container}
        role="application"
        aria-label={accessibilityLabel}
        data-testid="map-canvas"
        style={{ position: "absolute", top: 0, right: 0, bottom: 0, left: 0 }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  clip: { overflow: "hidden" },
});
