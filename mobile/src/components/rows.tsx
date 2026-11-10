// List rows with a single, fully labelled touch target (docs/07 §5).
import type { ReactNode } from "react";
import { Pressable, StyleSheet, View } from "react-native";

import { radius, spacing, TOUCH_TARGET, useTheme } from "../theme";
import { AppText } from "./ui";

interface ListRowProps {
  title: string;
  subtitle?: string | undefined;
  onPress: () => void;
  accessibilityLabel?: string;
  hint?: string;
  right?: ReactNode;
  testID?: string;
}

export function ListRow({ title, subtitle, onPress, accessibilityLabel, hint, right, testID }: ListRowProps) {
  const { colors } = useTheme();
  return (
    <View style={[styles.row, { borderColor: colors.border, backgroundColor: colors.surface }]}>
      <Pressable
        testID={testID}
        accessibilityRole="button"
        accessibilityLabel={accessibilityLabel ?? (subtitle ? `${title}. ${subtitle}` : title)}
        accessibilityHint={hint}
        onPress={onPress}
        style={({ pressed }) => [styles.main, pressed && styles.pressed]}
      >
        <AppText style={styles.title}>{title}</AppText>
        {subtitle ? (
          <AppText variant="small" muted>
            {subtitle}
          </AppText>
        ) : null}
      </Pressable>
      {right}
    </View>
  );
}

interface ChoiceRowProps {
  title: string;
  subtitle?: string | undefined;
  selected: boolean;
  onPress: () => void;
  hint?: string;
  testID?: string;
}

/** Single-choice option: the state is spoken and drawn as a filled or empty circle. */
export function ChoiceRow({ title, subtitle, selected, onPress, hint, testID }: ChoiceRowProps) {
  const { colors } = useTheme();
  return (
    <Pressable
      testID={testID}
      accessibilityRole="radio"
      accessibilityState={{ selected, checked: selected }}
      accessibilityLabel={subtitle ? `${title}. ${subtitle}` : title}
      accessibilityHint={hint}
      onPress={onPress}
      style={({ pressed }) => [
        styles.row,
        styles.choice,
        { borderColor: selected ? colors.primary : colors.border, backgroundColor: colors.surface },
        selected && styles.choiceSelected,
        pressed && styles.pressed,
      ]}
    >
      <View style={[styles.radio, { borderColor: selected ? colors.primary : colors.textMuted }]}>
        {selected ? <View style={[styles.radioDot, { backgroundColor: colors.primary }]} /> : null}
      </View>
      <View style={styles.choiceText}>
        <AppText style={styles.title}>{title}</AppText>
        {subtitle ? (
          <AppText variant="small" muted>
            {subtitle}
          </AppText>
        ) : null}
      </View>
    </Pressable>
  );
}

interface IconButtonProps {
  symbol: string;
  accessibilityLabel: string;
  hint?: string;
  onPress: () => void;
  testID?: string;
  selected?: boolean;
}

/** Compact square button; the symbol is decorative, the label is what gets spoken. */
export function IconButton({ symbol, accessibilityLabel, hint, onPress, testID, selected }: IconButtonProps) {
  const { colors } = useTheme();
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      accessibilityHint={hint}
      accessibilityState={selected === undefined ? {} : { selected }}
      onPress={onPress}
      style={({ pressed }) => [styles.icon, { borderColor: colors.border }, pressed && styles.pressed]}
    >
      <AppText variant="heading" color={selected ? colors.primary : colors.text}>
        {symbol}
      </AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
    borderWidth: 1,
    borderRadius: radius.md,
    minHeight: TOUCH_TARGET + 8,
  },
  main: { flex: 1, minHeight: TOUCH_TARGET, justifyContent: "center", paddingHorizontal: spacing.lg, paddingVertical: spacing.sm },
  title: { fontWeight: "600" },
  pressed: { opacity: 0.7 },
  choice: { paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, gap: spacing.md },
  choiceSelected: { borderWidth: 2 },
  choiceText: { flex: 1 },
  radio: { width: 24, height: 24, borderRadius: 12, borderWidth: 2, alignItems: "center", justifyContent: "center" },
  radioDot: { width: 12, height: 12, borderRadius: 6 },
  icon: {
    width: TOUCH_TARGET,
    height: TOUCH_TARGET,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: radius.sm,
    borderLeftWidth: StyleSheet.hairlineWidth,
  },
});
