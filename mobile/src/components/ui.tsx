// Shared building blocks. They centralise the accessibility rules of docs/07 §5:
// labelled controls, 48 dp targets, scalable text and sufficient contrast.
import type { ReactNode } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type TextProps,
  type TextStyle,
  type ViewStyle,
} from "react-native";
import { SafeAreaView, type Edge } from "react-native-safe-area-context";

import { radius, spacing, statusColor, TOUCH_TARGET, useTheme, type RouteStatus } from "../theme";

type TextVariant = "title" | "heading" | "body" | "small" | "big";

const textStyles: Record<TextVariant, TextStyle> = {
  big: { fontSize: 28, lineHeight: 36, fontWeight: "700" },
  title: { fontSize: 22, lineHeight: 30, fontWeight: "700" },
  heading: { fontSize: 18, lineHeight: 26, fontWeight: "600" },
  body: { fontSize: 16, lineHeight: 24 },
  small: { fontSize: 14, lineHeight: 20 },
};

interface AppTextProps extends TextProps {
  variant?: TextVariant;
  muted?: boolean;
  color?: string;
}

export function AppText({ variant = "body", muted = false, color, style, ...rest }: AppTextProps) {
  const { colors } = useTheme();
  return (
    <Text
      allowFontScaling
      maxFontSizeMultiplier={2}
      {...rest}
      style={[textStyles[variant], { color: color ?? (muted ? colors.textMuted : colors.text) }, style]}
    />
  );
}

interface ScreenProps {
  children: ReactNode;
  scroll?: boolean;
  edges?: Edge[];
  padded?: boolean;
}

export function Screen({ children, scroll = false, edges = ["bottom", "left", "right"], padded = true }: ScreenProps) {
  const { colors } = useTheme();
  const padding = padded ? { padding: spacing.lg } : null;
  return (
    <SafeAreaView edges={edges} style={[styles.flex, { backgroundColor: colors.background }]}>
      {scroll ? (
        <ScrollView contentContainerStyle={[padding, styles.scrollContent]} keyboardShouldPersistTaps="handled">
          {children}
        </ScrollView>
      ) : (
        <View style={[styles.flex, padding]}>{children}</View>
      )}
    </SafeAreaView>
  );
}

interface AppButtonProps {
  label: string;
  onPress: () => void;
  hint?: string;
  variant?: "primary" | "secondary" | "danger";
  disabled?: boolean;
  busy?: boolean;
  style?: StyleProp<ViewStyle>;
  testID?: string;
  /** Overrides the spoken label when the visible one is too terse. */
  accessibilityLabel?: string;
  selected?: boolean;
}

export function AppButton({
  label,
  onPress,
  hint,
  variant = "primary",
  disabled = false,
  busy = false,
  style,
  testID,
  accessibilityLabel,
  selected,
}: AppButtonProps) {
  const { colors } = useTheme();
  const background =
    variant === "primary" ? colors.primary : variant === "danger" ? colors.danger : colors.surfaceAlt;
  const foreground =
    variant === "primary" ? colors.onPrimary : variant === "danger" ? colors.onDanger : colors.text;
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityHint={hint}
      accessibilityState={{ disabled: disabled || busy, busy, ...(selected === undefined ? {} : { selected }) }}
      disabled={disabled || busy}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: background, borderColor: variant === "secondary" ? colors.border : background },
        (disabled || busy) && styles.disabled,
        pressed && styles.pressed,
        style,
      ]}
    >
      {busy ? <ActivityIndicator color={foreground} /> : null}
      <AppText style={styles.buttonLabel} color={foreground}>
        {label}
      </AppText>
    </Pressable>
  );
}

export function Card({ children, style }: { children: ReactNode; style?: StyleProp<ViewStyle> }) {
  const { colors } = useTheme();
  return (
    <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }, style]}>{children}</View>
  );
}

/** Status shown as colour, shape and text, so it never depends on colour alone. */
export function StatusBadge({ status, label }: { status: RouteStatus; label: string }) {
  const { colors } = useTheme();
  const color = statusColor(colors, status);
  const symbol = status === "accessible" ? "●" : status === "caution" ? "▲" : status === "inaccessible" ? "■" : "○";
  return (
    <View style={[styles.badge, { borderColor: color }]}>
      <AppText variant="small" color={color} accessibilityElementsHidden importantForAccessibility="no">
        {symbol}
      </AppText>
      <AppText variant="small" color={color} style={styles.badgeLabel}>
        {label}
      </AppText>
    </View>
  );
}

export function Notice({
  tone,
  title,
  body,
  children,
}: {
  tone: "info" | "warning" | "error";
  title: string;
  body?: string;
  children?: ReactNode;
}) {
  const { colors } = useTheme();
  const accent = tone === "error" ? colors.inaccessible : tone === "warning" ? colors.caution : colors.primary;
  return (
    <View
      accessibilityRole={tone === "info" ? "summary" : "alert"}
      style={[styles.notice, { backgroundColor: colors.surface, borderColor: accent }]}
    >
      <AppText variant="heading">{title}</AppText>
      {body ? <AppText>{body}</AppText> : null}
      {children}
    </View>
  );
}

export function Loading({ label }: { label: string }) {
  const { colors } = useTheme();
  return (
    <View style={styles.loading} accessibilityRole="progressbar" accessibilityLabel={label}>
      <ActivityIndicator size="large" color={colors.primary} />
      <AppText muted>{label}</AppText>
    </View>
  );
}

export function SectionTitle({ children }: { children: string }) {
  return (
    <AppText variant="heading" accessibilityRole="header" aria-level={2} style={styles.sectionTitle}>
      {children}
    </AppText>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  scrollContent: { gap: spacing.md, paddingBottom: spacing.xl * 2 },
  button: {
    minHeight: TOUCH_TARGET,
    minWidth: TOUCH_TARGET,
    borderRadius: radius.md,
    borderWidth: 1,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
  },
  buttonLabel: { fontWeight: "600", textAlign: "center", flexShrink: 1 },
  disabled: { opacity: 0.5 },
  pressed: { opacity: 0.8 },
  card: { borderWidth: 1, borderRadius: radius.md, padding: spacing.lg, gap: spacing.sm },
  badge: {
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "flex-start",
    gap: spacing.xs,
    borderWidth: 1.5,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
  },
  badgeLabel: { fontWeight: "600" },
  notice: { borderWidth: 2, borderRadius: radius.md, padding: spacing.lg, gap: spacing.sm },
  loading: { alignItems: "center", justifyContent: "center", gap: spacing.md, padding: spacing.xl },
  sectionTitle: { marginTop: spacing.md },
});
