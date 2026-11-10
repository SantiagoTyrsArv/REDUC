// Route planning (RF-01, RF-06, RF-07): routes with their numbers, the reason the shortest
// one is not used, every warning as text and an explicit answer when no route is accessible.
import type { Route, Shortest } from "@reduc/api-client";
import { useRouter } from "expo-router";
import { useEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { StyleSheet, View } from "react-native";

import { IconButton, ListRow } from "../../src/components/rows";
import { AppButton, AppText, Loading, Notice, Screen, SectionTitle } from "../../src/components/ui";
import { MapCanvas } from "../../src/features/map/MapCanvas";
import type { MapFocus, MapMarker } from "../../src/features/map/types";
import { toMapRoutes, uniqueWarnings } from "../../src/features/routes/plan";
import { RouteCard, useRouteSummary } from "../../src/features/routes/RouteCard";
import { usePlannedRoutes } from "../../src/features/routes/usePlannedRoutes";
import { announce } from "../../src/lib/a11y";
import { ApiProblem } from "../../src/lib/api";
import { formatDistance } from "../../src/lib/format";
import { boundsOf, type LonLat } from "../../src/lib/geo";
import { usePlanStore } from "../../src/stores/plan";
import { selectActiveProfile, useProfileStore } from "../../src/stores/profiles";
import { useRegionStore } from "../../src/stores/region";
import { useSettingsStore } from "../../src/stores/settings";
import { radius, spacing } from "../../src/theme";

const VIOLATED_KEYS = ["avoid_unverified", "curb_ramp_unknown", "surface_class", "slope"] as const;
type ViolatedKey = (typeof VIOLATED_KEYS)[number];

export default function RouteScreen() {
  const { t } = useTranslation();
  const router = useRouter();
  const units = useSettingsStore((state) => state.units);
  const showLayer = useSettingsStore((state) => state.showAccessibilityLayer);
  const region = useRegionStore((state) => state.region);
  const origin = usePlanStore((state) => state.origin);
  const destination = usePlanStore((state) => state.destination);
  const position = usePlanStore((state) => state.position);
  const active = useProfileStore(selectActiveProfile);
  const plan = usePlannedRoutes();
  const summary = useRouteSummary();
  const { routes, selected, result } = plan;

  const titleOf = (route: Route, index: number): string =>
    plan.isFallback ? t("route.fallback") : index === 0 ? t("route.recommended") : t("route.alternative", { n: index });

  // Speak the outcome once per calculation (docs/07 §5).
  const announced = useRef<unknown>(null);
  useEffect(() => {
    if (!result || announced.current === result) {
      return;
    }
    announced.current = result;
    if (result.kind === "ok" && result.data.routes[0]) {
      announce(
        t("route.announce", {
          count: result.data.routes.length,
          summary: summary(result.data.routes[0], t("route.recommended")),
        }),
      );
    } else if (result.kind === "no_accessible_route") {
      announce(`${t("route.noRouteTitle")}. ${result.error.detail}`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result]);

  const originPoint: LonLat | null = origin?.location ?? position;
  const mapRoutes = useMemo(() => toMapRoutes(routes, selected?.id ?? null), [routes, selected?.id]);
  const markers = useMemo<MapMarker[]>(() => {
    const list: MapMarker[] = [];
    if (originPoint) {
      list.push({ id: "origin", kind: "origin", location: originPoint });
    }
    if (destination) {
      list.push({ id: "destination", kind: "destination", location: destination.location });
    }
    return list;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [originPoint?.[0], originPoint?.[1], destination]);
  const focus = useMemo<MapFocus | null>(() => {
    const coords = selected
      ? (selected.geometry.coordinates as LonLat[])
      : [originPoint, destination?.location].filter((point): point is LonLat => Boolean(point));
    const bounds = boundsOf(coords);
    return bounds ? { kind: "bounds", bounds, key: `route:${selected?.id ?? "none"}:${bounds.join(",")}` } : null;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.id, originPoint?.[0], originPoint?.[1], destination]);

  const shortest: Shortest | null | undefined =
    result?.kind === "ok" ? result.data.shortest : result?.kind === "no_accessible_route" ? result.error.extra.shortest : null;
  const violated =
    result?.kind === "no_accessible_route"
      ? result.error.extra.violated_constraints.filter((key): key is ViolatedKey =>
          (VIOLATED_KEYS as readonly string[]).includes(key),
        )
      : [];
  const warnings = selected ? uniqueWarnings(selected) : [];

  const start = (route: Route) => {
    usePlanStore.getState().startNavigation(route);
    router.push("/navigate");
  };

  const shortestSection = () => {
    if (!shortest) {
      return null;
    }
    const reference = routes[0];
    const diff = reference ? reference.distance_m - shortest.distance_m : 0;
    const barriers = shortest.blocking_barriers;
    return (
      <View style={styles.section}>
        <SectionTitle>{t("route.shortestTitle")}</SectionTitle>
        {reference && !plan.isFallback && diff < 1 && barriers.length === 0 ? (
          <AppText>{t("route.shortestSame")}</AppText>
        ) : (
          <>
            <AppText>
              {t("route.shortestLonger", {
                distance: formatDistance(shortest.distance_m, units),
                diff: formatDistance(Math.max(0, diff), units),
              })}
            </AppText>
            {barriers.length > 0 ? (
              <AppText>{t("route.shortestBlocked", { count: barriers.length })}</AppText>
            ) : (
              <AppText>{t("route.shortestSoft")}</AppText>
            )}
            {barriers.map((barrier) => (
              <ListRow
                key={barrier.id}
                testID={`blocking-${barrier.id}`}
                title={barrier.message}
                hint={t("route.barrierHint")}
                onPress={() => router.push(`/barrier/${barrier.id}`)}
              />
            ))}
          </>
        )}
      </View>
    );
  };

  return (
    <Screen scroll>
      <View style={styles.endpoints}>
        <View style={styles.endpointList}>
          <ListRow
            testID="route-origin"
            title={t("route.originValue", { name: origin?.name ?? t("common.currentLocation") })}
            hint={t("route.changeHint")}
            onPress={() => router.push("/search?target=origin")}
          />
          <ListRow
            testID="route-destination"
            title={
              destination ? t("route.destinationValue", { name: destination.name }) : t("route.chooseDestination")
            }
            hint={t("route.changeHint")}
            onPress={() => router.push("/search?target=destination")}
          />
        </View>
        <IconButton
          testID="route-swap"
          symbol="⇅"
          accessibilityLabel={t("route.swap")}
          hint={t("route.swapHint")}
          onPress={() => usePlanStore.getState().swap(t("common.currentLocation"))}
        />
      </View>

      {active === null ? (
        <Notice tone="warning" title={t("route.needProfileTitle")} body={t("route.needProfileBody")}>
          <AppButton label={t("route.goProfiles")} onPress={() => router.push("/profiles")} />
        </Notice>
      ) : destination === null ? (
        <Notice tone="info" title={t("route.needDestinationTitle")} body={t("route.needDestinationBody")} />
      ) : originPoint === null ? (
        <Notice tone="warning" title={t("route.needOriginTitle")} body={t("route.needOriginBody")} />
      ) : null}

      {plan.isLoading ? <Loading label={t("route.calculating")} /> : null}

      {plan.error ? (
        <Notice
          tone="error"
          title={t("errors.title")}
          body={
            plan.error instanceof ApiProblem && plan.error.type !== "network_error"
              ? plan.error.message
              : t("errors.network")
          }
        >
          <AppButton testID="route-retry" label={t("common.retry")} onPress={plan.refetch} />
        </Notice>
      ) : null}

      {result?.kind === "no_accessible_route" ? (
        <Notice
          tone="error"
          title={t("route.noRouteTitle")}
          body={routes.length > 0 ? t("route.noRouteFallback") : t("route.noRouteNone")}
        >
          {violated.length > 0 ? (
            <View accessibilityRole="list">
              <AppText style={styles.bold}>{t("route.violatedTitle")}</AppText>
              {violated.map((key) => (
                <AppText key={key}>• {t(`route.violated.${key}`)}</AppText>
              ))}
            </View>
          ) : null}
        </Notice>
      ) : null}

      {routes.length > 0 ? (
        <>
          <MapCanvas
            style={styles.map}
            initialBounds={focus?.kind === "bounds" ? focus.bounds : (region?.bbox ?? null)}
            mapVersion={region?.map_version.number ?? null}
            showAccessibility={showLayer}
            routes={mapRoutes}
            markers={markers}
            focus={focus}
            onBarrierPress={(id) => router.push(`/barrier/${id}`)}
            accessibilityLabel={t("route.mapLabel")}
          />
          <View accessibilityRole="radiogroup" style={styles.section}>
            {routes.map((route, index) => (
              <RouteCard
                key={route.id}
                testID={`route-card-${index}`}
                route={route}
                title={titleOf(route, index)}
                selected={route.id === selected?.id}
                onSelect={() => usePlanStore.getState().selectRoute(route.id)}
              />
            ))}
          </View>
        </>
      ) : null}

      {selected ? (
        <View style={styles.section}>
          <SectionTitle>{t("route.warningsTitle")}</SectionTitle>
          {warnings.length === 0 ? (
            <AppText>{t("route.noWarnings")}</AppText>
          ) : (
            warnings.map((warning) => (
              <AppText key={warning.message} accessibilityLabel={`${t(`segments.severity.${warning.severity}`)}: ${warning.message}`}>
                {warning.severity === "major" ? "▲ " : "• "}
                {warning.message}
              </AppText>
            ))
          )}
        </View>
      ) : null}

      {shortestSection()}

      {selected ? (
        <View style={styles.actions}>
          <AppButton
            testID="route-segments"
            variant="secondary"
            style={styles.action}
            label={t("route.viewSegments")}
            hint={t("route.viewSegmentsHint")}
            onPress={() => router.push("/route/segments")}
          />
          <AppButton
            testID="route-start"
            variant={plan.isFallback ? "danger" : "primary"}
            style={styles.action}
            label={plan.isFallback ? t("route.startAnyway") : t("route.start")}
            hint={plan.isFallback ? t("route.startAnywayHint") : t("route.startHint")}
            onPress={() => start(selected)}
          />
        </View>
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  endpoints: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  endpointList: { flex: 1, gap: spacing.sm },
  section: { gap: spacing.sm },
  map: { height: 240, borderRadius: radius.md },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  action: { flexGrow: 1, flexBasis: 140 },
  bold: { fontWeight: "600" },
});
