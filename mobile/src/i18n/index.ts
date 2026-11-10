// i18next setup: Spanish by default, English as the alternative (docs/07 §1).
import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import { useSettingsStore, type Language } from "../stores/settings";
import { en } from "./en";
import { es } from "./es";

export const resources = { es: { translation: es }, en: { translation: en } } as const;

void i18n.use(initReactI18next).init({
  resources,
  lng: useSettingsStore.getState().language,
  fallbackLng: "es",
  interpolation: { escapeValue: false },
  returnNull: false,
});

// Keep i18next in sync with the persisted preference, including after rehydration.
useSettingsStore.subscribe((state) => {
  if (i18n.language !== state.language) {
    void i18n.changeLanguage(state.language);
  }
});

export function currentLanguage(): Language {
  return i18n.language === "en" ? "en" : "es";
}

export { i18n };
