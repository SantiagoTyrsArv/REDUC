// Linear, screen-reader friendly description of the selected route (docs/07 §5): every
// segment with its status, numbers and warnings, followed by the turn-by-turn directions.
import type { Segment } from "@reduc/api-client";
import { useRouter } from "expo-router";
import { useTranslation } from "react-i18next";
import { StyleSheet, View } from "react-native";

import { AppButton, AppText, Card, Loading, Notice, Screen, SectionTitle, StatusBadge } from "../../src/components/ui";
import { useSlopeText } from "../../src/features/routes/RouteCard";
import { usePlannedRoutes } from "../../src/features/routes/usePlannedRoutes";
import { formatDistance } from "../../src/lib/format";
import { usePlanStore } from "../../src/stores/plan";
import { useSettingsStore } from "../../src/stores/settings";
import { spacing } from "../../src/theme";

type SurfaceKey = "0" | "1" | "2" | "3" | "4";

export default function SegmentsScreen() {
  const { t } = useTranslation();
  const slopeText = useSlopeText();
  const router = useRouter();
  const units = useSettingsStore((state) => state.units);
  const activeRoute = usePlanStore((state) => state.activeRoute);
  const plan = usePlannedRoutes();
  // While navigating, describe the route actually being followed (it may have been recalculated).
  const route = activeRoute ?? plan.selected;

  if (route === null) {
    return (
      <Screen>
        {plan.isLoading ? (
          <Loading label={t("route.calculating")} />
        ) : (
          <Notice tone="info" title={t("segments.empty")}>
            <AppButton label={t("navigate.planRoute")} onPress={() => router.replace("/route")} />
          </Notice>
        )}
      </Screen>
    );
  }

  const total = route.segments.length;
  const surfaceName = (segment: Segment): string =>
    t(`segments.surfaceClass.${String(Math.min(4, Math.max(0, segment.surface_class))) as SurfaceKey}`);

  return (
    <Screen scroll>
      <AppText accessibilityRole="summary" testID="segments-intro">
        {t("segments.intro", { count: total, distance: formatDistance(route.distance_m, units) })}
      </AppText>

      <View accessibilityRole="list" style={styles.list}>
        {route.segments.map((segment, index) => {
          const slope = slopeText(segment.slope_pct);
          const distance = formatDistance(segment.distance_m, units);
          const warnings = segment.warnings.map((warning) => warning.message);
          return (
            <Card key={index}>
              <View
                accessible
                testID={`segment-${index}`}
                accessibilityLabel={t("segments.itemLabel", {
                  index: index + 1,
                  total,
                  status: t(`status.${segment.status}`),
                  distance,
                  slope,
                  surface: surfaceName(segment),
                  warnings: warnings.length > 0 ? warnings.join(". ") : t("segments.noWarnings"),
                })}
                style={styles.item}
              >
                <View style={styles.itemHeader}>
                  <AppText variant="heading" style={styles.itemTitle}>
                    {t("segments.item", { index: index + 1, total })}
                  </AppText>
                  <StatusBadge status={segment.status} label={t(`status.${segment.status}`)} />
                </View>
                <AppText>
                  {distance} · {t("segments.slope", { slope })} · {t("segments.surface", { surface: surfaceName(segment) })}
                </AppText>
                {segment.warnings.length === 0 ? (
                  <AppText muted>{t("segments.noWarnings")}</AppText>
                ) : (
                  segment.warnings.map((warning) => (
                    <AppText key={warning.code + warning.message}>
                      {warning.severity === "major" ? "▲ " : "• "}
                      {t(`segments.severity.${warning.severity}`)}: {warning.message}
                    </AppText>
                  ))
                )}
              </View>
            </Card>
          );
        })}
      </View>

      <SectionTitle>{t("segments.instructionsTitle")}</SectionTitle>
      <View accessibilityRole="list" style={styles.list}>
        {route.instructions.map((instruction, index) => (
          <AppText key={index} testID={`instruction-${index}`}>
            {index + 1}. {instruction.text}
          </AppText>
        ))}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  list: { gap: spacing.sm },
  item: { gap: spacing.xs },
  itemHeader: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: spacing.sm },
  itemTitle: { flexGrow: 1, flexShrink: 1 },
});
