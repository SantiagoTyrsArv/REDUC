// Settings: language, units, region, demo location and licences (docs/07 §2).
import Constants from "expo-constants";
import { useTranslation } from "react-i18next";
import { StyleSheet, Switch, View } from "react-native";

import { ChoiceRow } from "../src/components/rows";
import { AppText, Card, Screen, SectionTitle } from "../src/components/ui";
import { useRegions } from "../src/lib/api";
import { useSettingsStore } from "../src/stores/settings";
import { spacing, TOUCH_TARGET, useTheme } from "../src/theme";

export default function SettingsScreen() {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const regions = useRegions();
  const settings = useSettingsStore();
  const hint = t("settings.selectHint");

  const toggle = (
    key: "demoLocation" | "showAccessibilityLayer",
    label: string,
    help?: string,
  ) => (
    <Card>
      <View style={styles.toggleRow}>
        <AppText style={styles.toggleLabel}>{label}</AppText>
        <Switch
          testID={`settings-${key}`}
          value={settings[key]}
          onValueChange={(value) => settings.set({ [key]: value })}
          accessibilityLabel={label}
          {...(help ? { accessibilityHint: help } : {})}
          trackColor={{ true: colors.primary, false: colors.border }}
          style={styles.switch}
        />
      </View>
      {help ? (
        <AppText variant="small" muted>
          {help}
        </AppText>
      ) : null}
    </Card>
  );

  return (
    <Screen scroll>
      <SectionTitle>{t("settings.language")}</SectionTitle>
      <View accessibilityRole="radiogroup" style={styles.group}>
        <ChoiceRow
          testID="settings-language-es"
          title={t("settings.languageEs")}
          selected={settings.language === "es"}
          hint={hint}
          onPress={() => settings.set({ language: "es" })}
        />
        <ChoiceRow
          testID="settings-language-en"
          title={t("settings.languageEn")}
          selected={settings.language === "en"}
          hint={hint}
          onPress={() => settings.set({ language: "en" })}
        />
      </View>

      <SectionTitle>{t("settings.units")}</SectionTitle>
      <View accessibilityRole="radiogroup" style={styles.group}>
        <ChoiceRow
          testID="settings-units-metric"
          title={t("settings.metric")}
          selected={settings.units === "metric"}
          hint={hint}
          onPress={() => settings.set({ units: "metric" })}
        />
        <ChoiceRow
          testID="settings-units-imperial"
          title={t("settings.imperial")}
          selected={settings.units === "imperial"}
          hint={hint}
          onPress={() => settings.set({ units: "imperial" })}
        />
      </View>

      <SectionTitle>{t("settings.region")}</SectionTitle>
      <View accessibilityRole="radiogroup" style={styles.group}>
        <ChoiceRow
          testID="settings-region-auto"
          title={t("settings.regionAuto")}
          selected={settings.regionSlug === null}
          hint={hint}
          onPress={() => settings.set({ regionSlug: null })}
        />
        {regions.data?.map((region) => (
          <ChoiceRow
            key={region.id}
            testID={`settings-region-${region.slug}`}
            title={region.name}
            subtitle={t("settings.regionStats", {
              edges: region.stats.edges,
              verified: Math.round(region.stats.verified_pct),
            })}
            selected={settings.regionSlug === region.slug}
            hint={hint}
            onPress={() => settings.set({ regionSlug: region.slug })}
          />
        ))}
      </View>

      {toggle("showAccessibilityLayer", t("settings.layer"))}
      {toggle("demoLocation", t("settings.demo"), t("settings.demoHelp"))}

      <SectionTitle>{t("settings.about")}</SectionTitle>
      <Card>
        <AppText>
          {t("common.appName")} · {t("settings.version", { version: Constants.expoConfig?.version ?? "0.1.0" })}
        </AppText>
        <AppText variant="small" muted accessibilityRole="header">
          {t("settings.licenses")}
        </AppText>
        <AppText>{t("settings.licenseOsm")}</AppText>
        <AppText>{t("settings.licenseMapillary")}</AppText>
        <AppText>{t("settings.licenseBase")}</AppText>
      </Card>
    </Screen>
  );
}

const styles = StyleSheet.create({
  group: { gap: spacing.sm },
  toggleRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.md },
  toggleLabel: { flex: 1, fontWeight: "600" },
  switch: { minHeight: TOUCH_TARGET, minWidth: TOUCH_TARGET },
});
