// Basic turn-by-turn navigation (RF-10): large current instruction, distance, next warning
// and automatic recalculation. Everything shown on the map is also available as text.
import { useRouter } from "expo-router";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { StyleSheet, View } from "react-native";

import { AppButton, AppText, Loading, Notice, Screen } from "../src/components/ui";
import { MapCanvas } from "../src/features/map/MapCanvas";
import type { MapFocus, MapMarker } from "../src/features/map/types";
import { useNavigationSession } from "../src/features/navigation/useNavigationSession";
import { toMapRoutes } from "../src/features/routes/plan";
import { durationMinutes, formatDistance } from "../src/lib/format";
import { roundToGrid, type LonLat } from "../src/lib/geo";
import { usePlanStore } from "../src/stores/plan";
import { useRegionStore } from "../src/stores/region";
import { useSettingsStore } from "../src/stores/settings";
import { radius, spacing } from "../src/theme";

export default function NavigateScreen() {
  const { t } = useTranslation();
  const router = useRouter();
  const route = usePlanStore((state) => state.activeRoute);
  const position = usePlanStore((state) => state.position);
  const region = useRegionStore((state) => state.region);
  const units = useSettingsStore((state) => state.units);
  const showLayer = useSettingsStore((state) => state.showAccessibilityLayer);
  const demoLocation = useSettingsStore((state) => state.demoLocation);
  const { progress, recalc, simulating, toggleSimulation } = useNavigationSession();

  const mapRoutes = useMemo(() => (route ? toMapRoutes([route], route.id) : []), [route]);
  const markers = useMemo<MapMarker[]>(() => {
    const list: MapMarker[] = [];
    const end = route?.geometry.coordinates[route.geometry.coordinates.length - 1] as LonLat | undefined;
    if (end) {
      list.push({ id: "destination", kind: "destination", location: end });
    }
    if (position) {
      list.push({ id: "position", kind: "position", location: position });
    }
    return list;
  }, [route, position]);
  // Follow the user; the 5 m grid avoids moving the camera on every GPS fix.
  const followKey = position ? roundToGrid(position).join(",") : null;
  const focus = useMemo<MapFocus | null>(
    () => (position ? { kind: "center", center: position, zoom: 18, key: `follow:${followKey}` } : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [followKey],
  );

  const stop = (target: "/" | "/route") => {
    usePlanStore.getState().stopNavigation();
    router.dismissTo(target);
  };

  if (route === null) {
    return (
      <Screen>
        <Notice tone="info" title={t("navigate.noRoute")}>
          <AppButton label={t("navigate.planRoute")} onPress={() => router.replace("/route")} />
        </Notice>
      </Screen>
    );
  }

  const current = progress ? route.instructions[progress.currentIndex] : route.instructions[0];
  const remainingDistance = progress ? formatDistance(progress.remainingM, units) : formatDistance(route.distance_m, units);
  const remainingMinutes = durationMinutes(progress ? progress.remainingS : route.duration_s);

  return (
    <Screen scroll edges={["bottom", "left", "right"]}>
      <MapCanvas
        style={styles.map}
        initialBounds={region?.bbox ?? null}
        mapVersion={region?.map_version.number ?? null}
        showAccessibility={showLayer}
        routes={mapRoutes}
        markers={markers}
        focus={focus}
        accessibilityLabel={t("navigate.mapLabel")}
      />

      {progress?.hasArrived ? (
        <Notice tone="info" title={t("navigate.arrivedTitle")}>
          <AppButton
            testID="navigate-finish"
            label={t("navigate.finish")}
            hint={t("navigate.finishHint")}
            onPress={() => stop("/")}
          />
        </Notice>
      ) : (
        <>
          {position === null ? <Loading label={t("navigate.waitingLocation")} /> : null}

          <View accessible accessibilityLiveRegion="polite" testID="navigate-current" style={styles.block}>
            <AppText variant="small" muted>
              {t("navigate.current")}
            </AppText>
            <AppText variant="big">{current?.text ?? ""}</AppText>
          </View>

          {progress?.next ? (
            <View accessible testID="navigate-next" style={styles.block}>
              <AppText variant="small" muted>
                {t("navigate.next", { distance: formatDistance(progress.distanceToNextM, units) })}
              </AppText>
              <AppText variant="heading">{progress.next.text}</AppText>
            </View>
          ) : null}

          <AppText
            testID="navigate-remaining"
            accessibilityLabel={t("navigate.remainingLabel", {
              distance: remainingDistance,
              duration: t("common.minutes", { count: remainingMinutes }),
            })}
          >
            {t("navigate.remaining", {
              distance: remainingDistance,
              duration: t("common.minutesShort", { count: remainingMinutes }),
            })}
          </AppText>

          {progress?.upcomingWarning ? (
            <Notice
              tone="warning"
              title={
                progress.upcomingWarning.distanceM > 0
                  ? t("navigate.warningAhead", { distance: formatDistance(progress.upcomingWarning.distanceM, units) })
                  : t("navigate.warningNow")
              }
              body={progress.upcomingWarning.warning.message}
            />
          ) : null}

          {progress?.isOffRoute ? (
            <Notice
              tone={recalc === "failed" || recalc === "no_route" ? "error" : "warning"}
              title={t("navigate.offRoute", { distance: formatDistance(progress.offRouteM, units) })}
              body={
                recalc === "failed"
                  ? t("navigate.recalcFailed")
                  : recalc === "no_route"
                    ? t("navigate.recalcNoRoute")
                    : t("navigate.recalculating")
              }
            />
          ) : null}
        </>
      )}

      <View style={styles.actions}>
        {demoLocation && !progress?.hasArrived ? (
          <AppButton
            testID="navigate-simulate"
            variant="secondary"
            style={styles.action}
            label={simulating ? t("navigate.simulateStop") : t("navigate.simulate")}
            hint={t("navigate.simulateHint")}
            onPress={toggleSimulation}
          />
        ) : null}
        <AppButton
          testID="navigate-segments"
          variant="secondary"
          style={styles.action}
          label={t("navigate.viewSegments")}
          hint={t("route.viewSegmentsHint")}
          onPress={() => router.push("/route/segments")}
        />
        {progress?.hasArrived ? null : (
          <AppButton
            testID="navigate-stop"
            variant="danger"
            style={styles.action}
            label={t("navigate.stop")}
            hint={t("navigate.stopHint")}
            onPress={() => stop("/route")}
          />
        )}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  map: { height: 260, borderRadius: radius.md },
  block: { gap: spacing.xs },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  action: { flexGrow: 1, flexBasis: 140 },
});
