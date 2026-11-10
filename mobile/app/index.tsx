// Main map (docs/07 §2): accessibility layer, destination search and quick controls in the
// lower half of the screen, within thumb reach.
import { Redirect, useRouter } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { StyleSheet, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { AppButton, AppText, Loading, Notice } from "../src/components/ui";
import { LegendSheet } from "../src/features/map/Legend";
import { MapCanvas } from "../src/features/map/MapCanvas";
import type { MapFocus, MapMarker } from "../src/features/map/types";
import { announce } from "../src/lib/a11y";
import { useRegions } from "../src/lib/api";
import { geometryContains, type LonLat } from "../src/lib/geo";
import { placeFromPoint } from "../src/stores/places";
import { usePlanStore } from "../src/stores/plan";
import { selectActiveProfile, useProfileStore } from "../src/stores/profiles";
import { useRegionStore } from "../src/stores/region";
import { useSettingsStore } from "../src/stores/settings";
import { radius, spacing, useTheme } from "../src/theme";

export default function MapScreen() {
  const { t } = useTranslation();
  const router = useRouter();
  const { colors } = useTheme();
  const regions = useRegions();
  const region = useRegionStore((state) => state.region);
  const onboardingDone = useSettingsStore((state) => state.onboardingDone);
  const showLayer = useSettingsStore((state) => state.showAccessibilityLayer);
  const setSettings = useSettingsStore((state) => state.set);
  const active = useProfileStore(selectActiveProfile);
  const position = usePlanStore((state) => state.position);
  const pickTarget = usePlanStore((state) => state.pickTarget);
  const [legendOpen, setLegendOpen] = useState(false);
  const [focus, setFocus] = useState<MapFocus | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const regionKey = region ? `${region.id}:${region.map_version.number}` : null;
  useEffect(() => {
    if (region) {
      setFocus({ kind: "bounds", bounds: region.bbox, key: `region:${regionKey}` });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [regionKey]);

  const markers = useMemo<MapMarker[]>(
    () => (position ? [{ id: "position", kind: "position", location: position }] : []),
    [position],
  );

  if (!onboardingDone) {
    return <Redirect href="/onboarding" />;
  }

  const say = (text: string) => {
    setMessage(text);
    announce(text);
  };

  const onMapPress = (location: LonLat) => {
    if (pickTarget === null) {
      return;
    }
    if (region && !geometryContains(region.boundary, location)) {
      say(t("map.outsideRegion"));
      return;
    }
    const plan = usePlanStore.getState();
    const place = placeFromPoint(location, t("common.pointOnMap"));
    if (pickTarget === "origin") {
      plan.setOrigin(place);
    } else {
      plan.setDestination(place);
    }
    plan.setPickTarget(null);
    setMessage(null);
    router.push("/route");
  };

  const center = () => {
    if (!position) {
      say(t("map.centerUnavailable"));
      return;
    }
    setMessage(null);
    setFocus({ kind: "center", center: position, key: `center:${Date.now()}` });
  };

  return (
    <View style={[styles.flex, { backgroundColor: colors.background }]}>
      <MapCanvas
        initialBounds={region?.bbox ?? null}
        mapVersion={region?.map_version.number ?? null}
        showAccessibility={showLayer}
        markers={markers}
        focus={focus}
        onPress={onMapPress}
        onBarrierPress={(id) => router.push(`/barrier/${id}`)}
        accessibilityLabel={region ? t("map.label", { region: region.name }) : t("map.labelNoRegion")}
      />

      <SafeAreaView edges={["top", "left", "right"]} style={styles.top} pointerEvents="box-none">
        <View style={styles.topRow} pointerEvents="box-none">
          <AppButton
            testID="map-profile"
            variant="secondary"
            style={styles.chip}
            label={t("map.profile", { name: active?.name ?? "—" })}
            hint={t("map.profileHint")}
            onPress={() => router.push("/profiles")}
          />
          <AppButton
            testID="map-settings"
            variant="secondary"
            label={t("map.settings")}
            hint={t("map.settingsHint")}
            onPress={() => router.push("/settings")}
          />
        </View>
      </SafeAreaView>

      <SafeAreaView edges={["bottom", "left", "right"]} style={styles.bottom} pointerEvents="box-none">
        <View style={[styles.panel, { backgroundColor: colors.overlay, borderColor: colors.border }]}>
          {regions.isPending ? <Loading label={t("common.loading")} /> : null}
          {regions.isError ? (
            <Notice tone="error" title={t("errors.title")} body={t("errors.network")}>
              <AppButton label={t("common.retry")} onPress={() => void regions.refetch()} />
            </Notice>
          ) : null}
          {regions.isSuccess && regions.data.length === 0 ? (
            <Notice tone="info" title={t("errors.noRegion")} body={t("errors.noRegionHint")} />
          ) : null}
          {message ? (
            <AppText accessibilityLiveRegion="polite" testID="map-message">
              {message}
            </AppText>
          ) : null}

          {pickTarget ? (
            <>
              <AppText variant="heading" accessibilityRole="header" accessibilityLiveRegion="polite">
                {pickTarget === "origin" ? t("map.pickOrigin") : t("map.pickDestination")}
              </AppText>
              <AppButton
                testID="map-pick-cancel"
                variant="secondary"
                label={t("map.pickCancel")}
                onPress={() => usePlanStore.getState().setPickTarget(null)}
              />
            </>
          ) : (
            <AppButton
              testID="map-where-to"
              label={t("map.whereTo")}
              hint={t("map.whereToHint")}
              onPress={() => router.push("/search?target=destination")}
            />
          )}

          <View style={styles.actions}>
            <AppButton
              testID="map-layer"
              variant="secondary"
              style={styles.action}
              label={t("map.layerShort")}
              accessibilityLabel={showLayer ? t("map.layerOn") : t("map.layerOff")}
              hint={t("map.layerHint")}
              selected={showLayer}
              onPress={() => setSettings({ showAccessibilityLayer: !showLayer })}
            />
            <AppButton
              testID="map-center"
              variant="secondary"
              style={styles.action}
              label={t("map.center")}
              accessibilityLabel={t("map.centerLabel")}
              hint={t("map.centerHint")}
              onPress={center}
            />
            <AppButton
              testID="map-legend"
              variant="secondary"
              style={styles.action}
              label={t("map.legend")}
              hint={t("map.legendHint")}
              onPress={() => setLegendOpen(true)}
            />
          </View>
        </View>
      </SafeAreaView>

      <LegendSheet visible={legendOpen} onClose={() => setLegendOpen(false)} />
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  top: { position: "absolute", top: 0, left: 0, right: 0 },
  topRow: { flexDirection: "row", justifyContent: "space-between", gap: spacing.sm, padding: spacing.md },
  chip: { flexShrink: 1 },
  bottom: { position: "absolute", bottom: 0, left: 0, right: 0 },
  panel: {
    margin: spacing.md,
    padding: spacing.md,
    gap: spacing.sm,
    borderRadius: radius.lg,
    borderWidth: 1,
  },
  actions: { flexDirection: "row", gap: spacing.sm },
  action: { flex: 1, paddingHorizontal: spacing.sm },
});
