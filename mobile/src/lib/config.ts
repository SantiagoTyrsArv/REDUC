// Runtime configuration. Everything comes from EXPO_PUBLIC_* variables (docs/07 §6);
// the fallbacks only make local development work out of the box.
import { Platform } from "react-native";

// The Android emulator reaches the host machine through 10.0.2.2, not localhost.
const devHost = Platform.OS === "android" ? "10.0.2.2" : "localhost";

function env(value: string | undefined, fallback: string): string {
  return value && value.trim().length > 0 ? value.trim().replace(/\/$/, "") : fallback;
}

export const config = {
  apiUrl: env(process.env.EXPO_PUBLIC_API_URL, `http://${devHost}:8000`),
  tilesUrl: env(process.env.EXPO_PUBLIC_TILES_URL, `http://${devHost}:3000`),
  mapStyleUrl: env(process.env.EXPO_PUBLIC_MAP_STYLE_URL, "https://tiles.openfreemap.org/styles/liberty"),
} as const;
