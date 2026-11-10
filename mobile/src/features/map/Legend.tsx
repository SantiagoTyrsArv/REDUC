// Accessible legend of the accessibility layer, shown as a bottom sheet (docs/07 §4).
import { useTranslation } from "react-i18next";
import { Modal, Pressable, ScrollView, StyleSheet, View } from "react-native";

import { AppButton, AppText, SectionTitle } from "../../components/ui";
import { radius, spacing, useTheme, type RouteStatus } from "../../theme";
import { BARRIER_COLORS } from "./layers";

function LineSample({ status }: { status: RouteStatus }) {
  const { colors } = useTheme();
  const color = colors[status];
  const pieces = status === "accessible" ? [44] : status === "caution" ? [12, 12, 12] : status === "inaccessible" ? [4, 4, 4, 4, 4] : [44];
  return (
    <View style={styles.sample} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      {pieces.map((width, index) => (
        <View
          key={index}
          style={{ width, height: status === "unknown" ? 2 : 5, borderRadius: 3, backgroundColor: color }}
        />
      ))}
    </View>
  );
}

function DotSample({ color, thick }: { color: string; thick?: boolean }) {
  const { colors } = useTheme();
  return (
    <View style={styles.sample} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      <View
        style={[styles.dot, { backgroundColor: color, borderColor: colors.text, borderWidth: thick ? 4 : 1.5 }]}
      />
    </View>
  );
}

function Row({ sample, text }: { sample: React.ReactNode; text: string }) {
  return (
    <View style={styles.row} accessible accessibilityRole="text" accessibilityLabel={text}>
      {sample}
      <AppText style={styles.rowText}>{text}</AppText>
    </View>
  );
}

export function LegendContent() {
  const { t } = useTranslation();
  const { colors } = useTheme();
  return (
    <View style={styles.content}>
      <SectionTitle>{t("legend.paths")}</SectionTitle>
      <Row sample={<LineSample status="accessible" />} text={t("legend.accessible")} />
      <Row sample={<LineSample status="caution" />} text={t("legend.caution")} />
      <Row sample={<LineSample status="inaccessible" />} text={t("legend.inaccessible")} />
      <Row sample={<LineSample status="unknown" />} text={t("legend.unknown")} />
      <SectionTitle>{t("legend.barriers")}</SectionTitle>
      <Row sample={<DotSample color={BARRIER_COLORS.stairs} />} text={t("legend.stairs")} />
      <Row sample={<DotSample color={BARRIER_COLORS.curb} />} text={t("legend.curb")} />
      <Row sample={<DotSample color={BARRIER_COLORS.obstacle} />} text={t("legend.obstacle")} />
      <Row sample={<DotSample color={BARRIER_COLORS.surface} />} text={t("legend.surface")} />
      <Row sample={<DotSample color={colors.surfaceAlt} thick />} text={t("legend.verified")} />
      <Row sample={<DotSample color={colors.surfaceAlt} />} text={t("legend.unverified")} />
    </View>
  );
}

export function LegendSheet({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const { colors } = useTheme();
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.backdrop}>
        <Pressable
          style={StyleSheet.absoluteFill}
          onPress={onClose}
          accessibilityRole="button"
          accessibilityLabel={t("common.close")}
        />
        <View
          style={[styles.sheet, { backgroundColor: colors.background, borderColor: colors.border }]}
          accessibilityViewIsModal
        >
          <ScrollView contentContainerStyle={styles.sheetContent}>
            <AppText variant="title" accessibilityRole="header">
              {t("legend.title")}
            </AppText>
            <LegendContent />
            <AppButton label={t("common.close")} onPress={onClose} testID="legend-close" />
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.sm },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 32 },
  rowText: { flex: 1 },
  sample: { width: 48, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 4 },
  dot: { width: 20, height: 20, borderRadius: 10 },
  backdrop: { flex: 1, justifyContent: "flex-end", backgroundColor: "rgba(0,0,0,0.4)" },
  sheet: { maxHeight: "80%", borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, borderWidth: 1 },
  sheetContent: { padding: spacing.lg, gap: spacing.md },
});
