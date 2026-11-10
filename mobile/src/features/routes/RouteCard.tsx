// Summary of one route. The whole card is one radio option with a complete spoken summary,
// so the choice is understandable without seeing the map (docs/07 §5).
import type { Route } from "@reduc/api-client";
import { useTranslation } from "react-i18next";
import { Pressable, StyleSheet, View } from "react-native";

import { AppText, StatusBadge } from "../../components/ui";
import { durationMinutes, formatDistance } from "../../lib/format";
import { useSettingsStore } from "../../stores/settings";
import { radius, spacing, useTheme } from "../../theme";
import { formatNumber } from "../profiles/fields";
import { routeStatus } from "./plan";

/** Slopes are signed along the direction of travel; they are worded, never shown with a minus sign. */
export function useSlopeText(): (slopePct: number) => string {
  const { t, i18n } = useTranslation();
  return (slopePct) => {
    const magnitude = Math.abs(slopePct);
    if (magnitude < 0.05) {
      return t("route.slopeFlat");
    }
    return t(slopePct > 0 ? "route.slopeUp" : "route.slopeDown", { slope: formatNumber(magnitude, 1, i18n.language) });
  };
}

export function useRouteSummary(): (route: Route, title: string) => string {
  const { t } = useTranslation();
  const slopeText = useSlopeText();
  const units = useSettingsStore((state) => state.units);
  return (route, title) =>
    t("route.summary", {
      title,
      distance: formatDistance(route.distance_m, units),
      duration: t("common.minutes", { count: durationMinutes(route.duration_s) }),
      score: Math.round(route.accessibility_score),
      slope: slopeText(route.max_slope_pct),
    });
}

interface RouteCardProps {
  route: Route;
  title: string;
  selected: boolean;
  onSelect: () => void;
  testID?: string;
}

export function RouteCard({ route, title, selected, onSelect, testID }: RouteCardProps) {
  const { t } = useTranslation();
  const slopeText = useSlopeText();
  const { colors } = useTheme();
  const units = useSettingsStore((state) => state.units);
  const summary = useRouteSummary();
  const status = routeStatus(route);
  const caution = route.caution_segments > 0 ? t("route.cautionSegments", { count: route.caution_segments }) : "";

  const metric = (label: string, value: string) => (
    <View style={styles.metric}>
      <AppText variant="small" muted>
        {label}
      </AppText>
      <AppText style={styles.metricValue}>{value}</AppText>
    </View>
  );

  return (
    <Pressable
      testID={testID}
      accessibilityRole="radio"
      accessibilityState={{ selected, checked: selected }}
      accessibilityLabel={`${summary(route, title)} ${t(`status.${status}`)}. ${caution}`.trim()}
      accessibilityHint={t("route.selectHint")}
      onPress={onSelect}
      style={[
        styles.card,
        { backgroundColor: colors.surface, borderColor: selected ? colors.primary : colors.border },
        selected && styles.selected,
      ]}
    >
      <View style={styles.header}>
        <AppText variant="heading" style={styles.title}>
          {title}
        </AppText>
        <StatusBadge status={status} label={t(`status.${status}`)} />
      </View>
      <View style={styles.metrics}>
        {metric(t("route.distance"), formatDistance(route.distance_m, units))}
        {metric(t("route.duration"), t("common.minutesShort", { count: durationMinutes(route.duration_s) }))}
        {metric(t("route.score"), t("route.scoreValue", { score: Math.round(route.accessibility_score) }))}
        {metric(t("route.maxSlope"), slopeText(route.max_slope_pct))}
        {metric(t("route.verified"), `${Math.round(route.verified_pct)} %`)}
      </View>
      {caution ? <AppText variant="small">{caution}</AppText> : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { borderWidth: 1, borderRadius: radius.md, padding: spacing.lg, gap: spacing.sm },
  selected: { borderWidth: 3 },
  header: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: spacing.sm },
  title: { flexShrink: 1, flexGrow: 1 },
  metrics: { flexDirection: "row", flexWrap: "wrap", columnGap: spacing.xl, rowGap: spacing.sm },
  metric: { minWidth: 88 },
  metricValue: { fontWeight: "600" },
});
