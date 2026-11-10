// Native map renderer (Android/iOS) on MapLibre Native. MapCanvas.web.tsx is its web twin.
import {
  Camera,
  GeoJSONSource,
  Layer,
  Map,
  VectorSource,
  type CameraRef,
  type LayerProps,
} from "@maplibre/maplibre-react-native";
import { useEffect, useMemo, useRef } from "react";
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

const FIT_PADDING = { top: 72, right: 48, bottom: 72, left: 48 };

function renderLayers(defs: LayerDef[]) {
  // LayerDef is a structural subset of the style-spec layer accepted by <Layer>.
  return defs.map((def) => <Layer key={def.id} {...(def as unknown as LayerProps)} />);
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
  const camera = useRef<CameraRef>(null);

  const layers = useMemo(
    () => ({
      edges: edgeLayers(colors),
      barriers: barrierLayers(colors),
      alt: altRouteLayers(colors),
      route: routeLayers(colors),
      markers: markerLayers(colors),
    }),
    [colors],
  );
  const altData = useMemo(() => altRoutesData(routes), [routes]);
  const routeData = useMemo(() => selectedRouteData(routes), [routes]);
  const markerData = useMemo(() => markersData(markers), [markers]);

  const focusKey = focus?.key ?? null;
  useEffect(() => {
    if (!focus || !camera.current) {
      return;
    }
    if (focus.kind === "bounds") {
      camera.current.fitBounds(focus.bounds, { padding: FIT_PADDING, duration: 600 });
    } else {
      camera.current.easeTo({ center: focus.center, zoom: focus.zoom ?? 17, duration: 600 });
    }
    // The key alone decides when to move the camera.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusKey]);

  return (
    <View style={[style ?? styles.fill, styles.clip]}>
      <Map
        style={styles.map}
        mapStyle={config.mapStyleUrl}
        attribution
        compass
        accessibilityLabel={accessibilityLabel}
        onPress={(event) => onPress?.([event.nativeEvent.lngLat[0], event.nativeEvent.lngLat[1]])}
      >
        <Camera
          ref={camera}
          {...(initialBounds ? { initialViewState: { bounds: initialBounds, padding: FIT_PADDING } } : {})}
        />
        {showAccessibility ? (
          <VectorSource
            id={EDGE_SOURCE}
            key={`${EDGE_SOURCE}-${mapVersion}`}
            tiles={[tileUrl(config.tilesUrl, "edge_accessibility", mapVersion)]}
            minzoom={10}
            maxzoom={18}
          >
            {renderLayers(layers.edges)}
          </VectorSource>
        ) : null}
        <GeoJSONSource id={ALT_ROUTES_SOURCE} data={altData}>
          {renderLayers(layers.alt)}
        </GeoJSONSource>
        <GeoJSONSource id={ROUTE_SOURCE} data={routeData}>
          {renderLayers(layers.route)}
        </GeoJSONSource>
        {showAccessibility ? (
          <VectorSource
            id={BARRIER_SOURCE}
            key={`${BARRIER_SOURCE}-${mapVersion}`}
            tiles={[tileUrl(config.tilesUrl, "barrier", mapVersion)]}
            minzoom={10}
            maxzoom={18}
            hitbox={{ top: 24, right: 24, bottom: 24, left: 24 }}
            onPress={(event) => {
              const id = event.nativeEvent.features[0]?.properties?.id;
              if (typeof id === "string" && onBarrierPress) {
                event.stopPropagation();
                onBarrierPress(id);
              }
            }}
          >
            {renderLayers(layers.barriers)}
          </VectorSource>
        ) : null}
        <GeoJSONSource id={MARKER_SOURCE} data={markerData}>
          {renderLayers(layers.markers)}
        </GeoJSONSource>
      </Map>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  clip: { overflow: "hidden" },
  map: { flex: 1 },
});
