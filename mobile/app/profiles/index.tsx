// Mobility profiles (RF-08): choose the active one, edit, delete and create from a template.
import { useRouter } from "expo-router";
import { useTranslation } from "react-i18next";
import { StyleSheet, View } from "react-native";

import { IconButton, ListRow } from "../../src/components/rows";
import { AppButton, AppText, Card, Loading, Notice, Screen, SectionTitle } from "../../src/components/ui";
import { usePresets } from "../../src/lib/api";
import { selectActiveProfile, useProfileStore } from "../../src/stores/profiles";
import { spacing } from "../../src/theme";

export default function ProfilesScreen() {
  const { t } = useTranslation();
  const router = useRouter();
  const presets = usePresets();
  const profiles = useProfileStore((state) => state.profiles);
  const active = useProfileStore(selectActiveProfile);
  const setActive = useProfileStore((state) => state.setActive);
  const removeProfile = useProfileStore((state) => state.removeProfile);
  const addProfile = useProfileStore((state) => state.addProfile);

  return (
    <Screen scroll>
      <SectionTitle>{t("profiles.activeTitle")}</SectionTitle>
      <AppText muted>{t("profiles.stored")}</AppText>
      {profiles.length === 0 ? <AppText>{t("profiles.empty")}</AppText> : null}
      {profiles.map((item) => {
        const isActive = item.id === active?.id;
        return (
          <Card key={item.id}>
            <View style={styles.header}>
              <AppText
                variant="heading"
                style={styles.name}
                accessibilityLabel={t(isActive ? "profiles.activeLabel" : "profiles.inactiveLabel", { name: item.name })}
              >
                {item.name}
              </AppText>
              {isActive ? <AppText testID={`profile-active-${item.id}`}>● {t("profiles.active")}</AppText> : null}
            </View>
            <AppText variant="small" muted>
              {t(`presets.${item.profile.device}`)}
            </AppText>
            <View style={styles.actions}>
              {isActive ? null : (
                <AppButton
                  testID={`profile-activate-${item.id}`}
                  style={styles.action}
                  label={t("profiles.activate")}
                  hint={t("profiles.activateHint")}
                  onPress={() => setActive(item.id)}
                />
              )}
              <AppButton
                testID={`profile-edit-${item.id}`}
                variant="secondary"
                style={styles.action}
                label={t("common.edit")}
                accessibilityLabel={`${t("common.edit")} ${item.name}`}
                hint={t("profiles.editHint")}
                onPress={() => router.push(`/profiles/${item.id}`)}
              />
              {profiles.length > 1 ? (
                <IconButton
                  testID={`profile-delete-${item.id}`}
                  symbol="✕"
                  accessibilityLabel={t("profiles.deleteLabel", { name: item.name })}
                  hint={t("profiles.deleteHint")}
                  onPress={() => removeProfile(item.id)}
                />
              ) : null}
            </View>
          </Card>
        );
      })}

      <SectionTitle>{t("profiles.createTitle")}</SectionTitle>
      {presets.isPending ? <Loading label={t("common.loading")} /> : null}
      {presets.isError ? (
        <Notice tone="error" title={t("errors.title")} body={t("errors.network")}>
          <AppButton label={t("common.retry")} onPress={() => void presets.refetch()} />
        </Notice>
      ) : null}
      {presets.data?.map((preset) => (
        <ListRow
          key={preset.id}
          testID={`profile-create-${preset.id}`}
          title={t(`presets.${preset.id}`)}
          hint={t("profiles.createHint")}
          onPress={() => {
            const id = addProfile(t(`presets.${preset.id}`), preset.profile);
            router.push(`/profiles/${id}`);
          }}
        />
      ))}
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: spacing.sm },
  name: { flexGrow: 1, flexShrink: 1 },
  actions: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: spacing.sm },
  action: { flexGrow: 1 },
});
