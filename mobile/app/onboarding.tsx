// First-run welcome: what the app does, location permission and a profile template (RF-08).
import type { Preset } from "@reduc/api-client";
import { useRouter } from "expo-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import { ChoiceRow } from "../src/components/rows";
import { AppButton, AppText, Loading, Notice, Screen, SectionTitle } from "../src/components/ui";
import { useLocationStore } from "../src/features/location/store";
import { requestLocationPermission } from "../src/features/location/useLocation";
import { formatNumber } from "../src/features/profiles/fields";
import { usePresets } from "../src/lib/api";
import { useProfileStore } from "../src/stores/profiles";
import { useSettingsStore } from "../src/stores/settings";
import { spacing } from "../src/theme";

export default function OnboardingScreen() {
  const { t, i18n } = useTranslation();
  const router = useRouter();
  const presets = usePresets();
  const permission = useLocationStore((state) => state.permission);
  const [chosen, setChosen] = useState<Preset["id"] | null>(null);
  const [asking, setAsking] = useState(false);

  const finish = () => {
    const preset = presets.data?.find((item) => item.id === chosen);
    if (!preset) {
      return;
    }
    const profiles = useProfileStore.getState();
    const id = profiles.addProfile(t(`presets.${preset.id}`), preset.profile);
    profiles.setActive(id);
    useSettingsStore.getState().set({ onboardingDone: true });
    router.replace("/");
  };

  return (
    <Screen scroll edges={["top", "bottom", "left", "right"]}>
      <AppText variant="big" accessibilityRole="header">
        {t("onboarding.title")}
      </AppText>
      <AppText>{t("onboarding.intro")}</AppText>
      <AppText muted>{t("onboarding.safety")}</AppText>

      <SectionTitle>{t("onboarding.locationTitle")}</SectionTitle>
      <AppText>{t("onboarding.locationBody")}</AppText>
      {permission === "granted" ? (
        <AppText accessibilityLiveRegion="polite">✓ {t("onboarding.locationGranted")}</AppText>
      ) : (
        <AppButton
          testID="onboarding-location"
          variant="secondary"
          label={t("onboarding.locationButton")}
          hint={t("onboarding.locationHint")}
          busy={asking}
          onPress={() => {
            setAsking(true);
            void requestLocationPermission().finally(() => setAsking(false));
          }}
        />
      )}
      {permission === "denied" ? (
        <AppText muted accessibilityLiveRegion="polite">
          {t("onboarding.locationDenied")}
        </AppText>
      ) : null}

      <SectionTitle>{t("onboarding.profileTitle")}</SectionTitle>
      <AppText>{t("onboarding.profileBody")}</AppText>
      {presets.isPending ? <Loading label={t("common.loading")} /> : null}
      {presets.isError ? (
        <Notice tone="error" title={t("errors.title")} body={t("errors.network")}>
          <AppButton label={t("common.retry")} onPress={() => void presets.refetch()} />
        </Notice>
      ) : null}
      <View accessibilityRole="radiogroup" style={{ gap: spacing.sm }}>
        {presets.data?.map((preset) => (
          <ChoiceRow
            key={preset.id}
            testID={`preset-${preset.id}`}
            title={t(`presets.${preset.id}`)}
            subtitle={t("presets.summary", {
              uphill: formatNumber(preset.profile.max_uphill_pct, 1, i18n.language),
              step: formatNumber(preset.profile.max_step_cm, 1, i18n.language),
              width: formatNumber(preset.profile.min_width_m, 2, i18n.language),
            })}
            selected={chosen === preset.id}
            hint={t("onboarding.profileHint")}
            onPress={() => setChosen(preset.id)}
          />
        ))}
      </View>

      <AppButton
        testID="onboarding-start"
        label={t("onboarding.start")}
        hint={chosen ? t("onboarding.startHint") : t("onboarding.chooseFirst")}
        disabled={chosen === null}
        onPress={finish}
      />
    </Screen>
  );
}
