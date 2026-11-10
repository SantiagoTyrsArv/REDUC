// Profile editor: every limit has a slider, step buttons, its value as text and an
// explanation, so it never relies on colour or on precise dragging (docs/07 §2 and §5).
import Slider from "@react-native-community/slider";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useTranslation } from "react-i18next";
import { StyleSheet, Switch, TextInput, View } from "react-native";

import { IconButton } from "../../src/components/rows";
import { AppButton, AppText, Card, Notice, Screen, SectionTitle } from "../../src/components/ui";
import {
  BOOLEAN_FIELDS,
  NUMERIC_FIELDS,
  formatNumber,
  getNumeric,
  setNumeric,
  type NumericField,
} from "../../src/features/profiles/fields";
import { useProfileStore } from "../../src/stores/profiles";
import { radius, spacing, TOUCH_TARGET, useTheme } from "../../src/theme";

type SurfaceKey = "0" | "1" | "2" | "3" | "4";

export default function EditProfileScreen() {
  const { t, i18n } = useTranslation();
  const router = useRouter();
  const { colors } = useTheme();
  const { id } = useLocalSearchParams<{ id: string }>();
  const stored = useProfileStore((state) => state.profiles.find((item) => item.id === id));
  const updateProfile = useProfileStore((state) => state.updateProfile);

  if (!stored) {
    return (
      <Screen>
        <Notice tone="info" title={t("profiles.notFound")}>
          <AppButton label={t("nav.profiles")} onPress={() => router.replace("/profiles")} />
        </Notice>
      </Screen>
    );
  }

  const profile = stored.profile;

  const numeric = (field: NumericField) => {
    const value = getNumeric(profile, field.key);
    const label = t(`profiles.fields.${field.key}.label`);
    const shown = formatNumber(value, field.decimals, i18n.language);
    const valueText =
      field.key === "max_surface_class"
        ? t("profiles.fields.max_surface_class.value", {
            value: shown,
            name: t(`segments.surfaceClass.${String(value) as SurfaceKey}`),
          })
        : t(`profiles.fields.${field.key}.value`, { value: shown });
    const change = (next: number) => updateProfile(stored.id, { profile: setNumeric(profile, field, next) });
    return (
      <Card key={field.key}>
        <View style={styles.fieldHeader}>
          <AppText style={styles.fieldLabel}>{label}</AppText>
          <AppText variant="heading" testID={`value-${field.key}`} accessibilityLiveRegion="polite">
            {valueText}
          </AppText>
        </View>
        <AppText variant="small" muted>
          {t(`profiles.fields.${field.key}.help`)}
        </AppText>
        <View style={styles.sliderRow}>
          <IconButton
            testID={`decrease-${field.key}`}
            symbol="−"
            accessibilityLabel={t("profiles.decrease", { label })}
            onPress={() => change(value - field.step)}
          />
          <Slider
            testID={`slider-${field.key}`}
            style={styles.slider}
            minimumValue={field.min}
            maximumValue={field.max}
            step={field.step}
            value={value}
            onValueChange={change}
            minimumTrackTintColor={colors.primary}
            maximumTrackTintColor={colors.border}
            thumbTintColor={colors.primary}
            accessibilityLabel={`${label}: ${valueText}`}
            accessibilityHint={t("profiles.sliderHint")}
          />
          <IconButton
            testID={`increase-${field.key}`}
            symbol="+"
            accessibilityLabel={t("profiles.increase", { label })}
            onPress={() => change(value + field.step)}
          />
        </View>
      </Card>
    );
  };

  return (
    <Screen scroll>
      <AppText style={styles.fieldLabel} nativeID="profile-name-label">
        {t("profiles.name")}
      </AppText>
      <TextInput
        testID="profile-name"
        value={stored.name}
        onChangeText={(name) => updateProfile(stored.id, { name })}
        accessibilityLabel={t("profiles.name")}
        accessibilityHint={t("profiles.nameHint")}
        accessibilityLabelledBy="profile-name-label"
        allowFontScaling
        maxFontSizeMultiplier={2}
        style={[styles.input, { color: colors.text, borderColor: colors.border, backgroundColor: colors.surface }]}
      />

      <SectionTitle>{t("profiles.limits")}</SectionTitle>
      {NUMERIC_FIELDS.filter((field) => field.group === "limits").map(numeric)}
      {BOOLEAN_FIELDS.map((key) => (
        <Card key={key}>
          <View style={styles.fieldHeader}>
            <AppText style={styles.fieldLabel}>{t(`profiles.fields.${key}.label`)}</AppText>
            <Switch
              testID={`switch-${key}`}
              value={profile[key]}
              onValueChange={(value) => updateProfile(stored.id, { profile: { ...profile, [key]: value } })}
              accessibilityLabel={t(`profiles.fields.${key}.label`)}
              accessibilityHint={t(`profiles.fields.${key}.help`)}
              trackColor={{ true: colors.primary, false: colors.border }}
              style={styles.switch}
            />
          </View>
          <AppText variant="small" muted>
            {t(`profiles.fields.${key}.help`)}
          </AppText>
        </Card>
      ))}

      <SectionTitle>{t("profiles.preferences")}</SectionTitle>
      {NUMERIC_FIELDS.filter((field) => field.group === "preferences").map(numeric)}

      <AppButton testID="profile-done" label={t("common.done")} onPress={() => router.back()} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  input: {
    minHeight: TOUCH_TARGET + 4,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    fontSize: 16,
  },
  fieldHeader: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: spacing.sm },
  fieldLabel: { fontWeight: "600", flexShrink: 1 },
  sliderRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  slider: { flex: 1, minHeight: TOUCH_TARGET },
  switch: { minHeight: TOUCH_TARGET, minWidth: TOUCH_TARGET },
});
