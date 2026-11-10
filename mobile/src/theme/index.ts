// Light and dark palettes. Every text/background pair below keeps a contrast ratio of at
// least 4.5:1 (docs/07 §5); status colours are always paired with a text label or pattern.
import { useColorScheme } from "react-native";

export interface Palette {
  background: string;
  surface: string;
  surfaceAlt: string;
  border: string;
  text: string;
  textMuted: string;
  primary: string;
  onPrimary: string;
  danger: string;
  onDanger: string;
  accessible: string;
  caution: string;
  inaccessible: string;
  unknown: string;
  overlay: string;
}

export const lightPalette: Palette = {
  background: "#ffffff",
  surface: "#f6f8fa",
  surfaceAlt: "#eaeef2",
  border: "#8c959f",
  text: "#1f2328",
  textMuted: "#57606a",
  primary: "#0b57d0",
  onPrimary: "#ffffff",
  danger: "#b3261e",
  onDanger: "#ffffff",
  accessible: "#1a7f37",
  caution: "#8a5a00",
  inaccessible: "#b3261e",
  unknown: "#57606a",
  overlay: "rgba(255,255,255,0.96)",
};

export const darkPalette: Palette = {
  background: "#0d1117",
  surface: "#161b22",
  surfaceAlt: "#21262d",
  border: "#8b949e",
  text: "#f0f6fc",
  textMuted: "#b1bac4",
  primary: "#8ab4f8",
  onPrimary: "#0d1117",
  danger: "#ffb4ab",
  onDanger: "#0d1117",
  accessible: "#56d364",
  caution: "#e3b341",
  inaccessible: "#ff9b94",
  unknown: "#b1bac4",
  overlay: "rgba(13,17,23,0.96)",
};

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24 } as const;
export const radius = { sm: 8, md: 12, lg: 20 } as const;
/** Minimum touch target in dp (RNF-06). */
export const TOUCH_TARGET = 48;

export function useTheme(): { colors: Palette; isDark: boolean } {
  const isDark = useColorScheme() === "dark";
  return { colors: isDark ? darkPalette : lightPalette, isDark };
}

export type RouteStatus = "accessible" | "caution" | "inaccessible" | "unknown";

export function statusColor(colors: Palette, status: RouteStatus): string {
  return colors[status];
}
