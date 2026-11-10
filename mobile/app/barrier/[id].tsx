// Barrier details (RF-07): what it is, how sure we are, who verified it and the attribution.
import { useLocalSearchParams } from "expo-router";
import { useTranslation } from "react-i18next";
import { Image, StyleSheet, View } from "react-native";

import { AppButton, AppText, Card, Loading, Notice, Screen } from "../../src/components/ui";
import { ApiProblem, useBarrier } from "../../src/lib/api";
import { radius, spacing, useTheme } from "../../src/theme";

const CLASSES = [
  "stairs",
  "single_step",
  "curb_no_ramp",
  "obstacle",
  "surface_damage",
  "steep_slope_visual",
  "no_sidewalk",
  "narrow_sidewalk",
] as const;
const VERIFICATION = ["confirmed", "unverified", "rejected", "manual"] as const;
const SOURCES = ["cv", "manual", "osm", "seed"] as const;

function known<T extends string>(values: readonly T[], value: string): T | null {
  return (values as readonly string[]).includes(value) ? (value as T) : null;
}

export default function BarrierScreen() {
  const { t, i18n } = useTranslation();
  const { colors } = useTheme();
  const { id } = useLocalSearchParams<{ id: string }>();
  const barrier = useBarrier(id, i18n.language === "en" ? "en" : "es");

  if (barrier.isPending) {
    return (
      <Screen>
        <Loading label={t("common.loading")} />
      </Screen>
    );
  }
  if (barrier.isError || !barrier.data) {
    const missing = barrier.error instanceof ApiProblem && barrier.error.status === 404;
    return (
      <Screen>
        <Notice tone="error" title={t("errors.title")} body={missing ? t("errors.notFound") : t("errors.network")}>
          {missing ? null : <AppButton label={t("common.retry")} onPress={() => void barrier.refetch()} />}
        </Notice>
      </Screen>
    );
  }

  const data = barrier.data;
  const verification = known(VERIFICATION, data.verification_status);
  const source = known(SOURCES, data.source);
  const row = (label: string, value: string, testID?: string) => (
    <View accessible accessibilityLabel={`${label}: ${value}`} style={styles.row} testID={testID}>
      <AppText variant="small" muted>
        {label}
      </AppText>
      <AppText style={styles.value}>{value}</AppText>
    </View>
  );

  return (
    <Screen scroll>
      <AppText variant="title" accessibilityRole="header" testID="barrier-title">
        {data.description}
      </AppText>

      {data.photo_url ? (
        <Image
          source={{ uri: data.photo_url }}
          accessible
          accessibilityRole="image"
          accessibilityLabel={t("barrier.photoLabel", { description: data.description })}
          resizeMode="cover"
          style={[styles.photo, { backgroundColor: colors.surfaceAlt }]}
        />
      ) : (
        <AppText muted>{t("barrier.noPhoto")}</AppText>
      )}

      <Card>
        {row(t("barrier.type"), t(`barrier.class.${known(CLASSES, data.class) ?? "other"}`))}
        {row(t("barrier.severity"), t(`barrier.severityValue.${data.severity}`), "barrier-severity")}
        {row(t("barrier.confidence"), t("barrier.confidenceValue", { pct: Math.round(data.confidence * 100) }))}
        {row(
          t("barrier.verification"),
          verification ? t(`barrier.verificationValue.${verification}`) : data.verification_status,
        )}
        {row(t("barrier.observationsLabel"), t("barrier.observations", { count: data.n_observations }))}
        {row(t("barrier.source"), source ? t(`barrier.sourceValue.${source}`) : data.source)}
      </Card>

      <Card>
        <AppText variant="small" muted accessibilityRole="header">
          {t("barrier.attribution")}
        </AppText>
        {data.attribution ? <AppText>{data.attribution}</AppText> : null}
        {data.source === "mapillary" && !data.attribution ? <AppText>{t("barrier.mapillaryAttribution")}</AppText> : null}
        <AppText>{t("barrier.osmAttribution")}</AppText>
      </Card>
    </Screen>
  );
}

const styles = StyleSheet.create({
  photo: { width: "100%", aspectRatio: 4 / 3, borderRadius: radius.md },
  row: { gap: 2, paddingVertical: spacing.xs },
  value: { fontWeight: "600" },
});
