// User preferences that survive restarts.
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import { appStorage } from "../lib/storage";

export type Language = "es" | "en";
export type Units = "metric" | "imperial";

interface SettingsState {
  language: Language;
  units: Units;
  onboardingDone: boolean;
  /** Region chosen by hand; null = detect from the user's position. */
  regionSlug: string | null;
  showAccessibilityLayer: boolean;
  /** Places the user inside the active region so the app can be tried from anywhere. */
  demoLocation: boolean;
  set: (changes: Partial<Omit<SettingsState, "set">>) => void;
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      language: "es",
      units: "metric",
      onboardingDone: false,
      regionSlug: null,
      showAccessibilityLayer: true,
      demoLocation: false,
      set: (changes) => set(changes),
    }),
    { name: "settings", storage: createJSONStorage(() => appStorage) },
  ),
);
