import { i18n } from "../src/i18n";
import { en } from "../src/i18n/en";
import { es } from "../src/i18n/es";
import { MAX_RECENTS, placeFromPoint, usePlacesStore } from "../src/stores/places";
import { usePlanStore } from "../src/stores/plan";
import { selectActiveProfile, useProfileStore } from "../src/stores/profiles";
import { useSettingsStore } from "../src/stores/settings";
import { manualProfile, resetStores, route } from "./helpers";

function keysOf(value: unknown, prefix = ""): string[] {
  if (typeof value === "string") {
    return [prefix];
  }
  return Object.entries(value as Record<string, unknown>).flatMap(([key, child]) =>
    keysOf(child, prefix ? `${prefix}.${key}` : key),
  );
}

function placeholders(text: string): string[] {
  return [...text.matchAll(/{{(\w+)}}/g)].map((match) => match[1]!).sort();
}

function lookup(source: unknown, key: string): string {
  return key.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown>)[part], source) as string;
}

beforeEach(resetStores);

describe("i18n catalogs", () => {
  it("has the same keys in Spanish and English", () => {
    expect(keysOf(en).sort()).toEqual(keysOf(es).sort());
  });

  it("uses the same placeholders in both languages and no empty texts", () => {
    for (const key of keysOf(es)) {
      expect(lookup(es, key).trim()).not.toBe("");
      expect(lookup(en, key).trim()).not.toBe("");
      expect({ key, vars: placeholders(lookup(en, key)) }).toEqual({ key, vars: placeholders(lookup(es, key)) });
    }
  });

  it("follows the language stored in settings", async () => {
    expect(i18n.t("map.whereTo")).toBe("¿A dónde vas?");
    useSettingsStore.getState().set({ language: "en" });
    await Promise.resolve();
    expect(i18n.t("map.whereTo")).toBe("Where to?");
    expect(i18n.t("common.minutes", { count: 1 })).toBe("1 minute");
    expect(i18n.t("common.minutes", { count: 4 })).toBe("4 minutes");
    useSettingsStore.getState().set({ language: "es" });
    await Promise.resolve();
    expect(i18n.t("route.cautionSegments", { count: 2 })).toBe("2 tramos con precaución");
  });
});

describe("profile store", () => {
  it("activates the first profile and falls back when the active one is removed", () => {
    useProfileStore.setState({ profiles: [], activeProfileId: null });
    const first = useProfileStore.getState().addProfile("Uno", manualProfile);
    const second = useProfileStore.getState().addProfile("Dos", manualProfile);
    expect(selectActiveProfile(useProfileStore.getState())?.id).toBe(first);
    useProfileStore.getState().setActive(second);
    useProfileStore.getState().updateProfile(second, { name: "Dos bis" });
    expect(selectActiveProfile(useProfileStore.getState())?.name).toBe("Dos bis");
    useProfileStore.getState().removeProfile(second);
    expect(selectActiveProfile(useProfileStore.getState())?.id).toBe(first);
    useProfileStore.getState().removeProfile(first);
    expect(selectActiveProfile(useProfileStore.getState())).toBeNull();
  });
});

describe("places store", () => {
  it("keeps at most 20 recents without duplicates and toggles favourites", () => {
    const places = usePlacesStore.getState();
    for (let i = 0; i < MAX_RECENTS + 5; i += 1) {
      places.addRecent({ id: `poi-${i}`, name: `Lugar ${i}`, location: [i, i] });
    }
    places.addRecent({ id: "poi-10", name: "Lugar 10", location: [10, 10] });
    const recents = usePlacesStore.getState().recents;
    expect(recents).toHaveLength(MAX_RECENTS);
    expect(recents[0]?.id).toBe("poi-10");
    expect(recents.filter((place) => place.id === "poi-10")).toHaveLength(1);

    const pin = placeFromPoint([1.234567, 2.345678], "Punto");
    places.toggleFavorite(pin);
    expect(usePlacesStore.getState().favorites).toEqual([pin]);
    places.toggleFavorite(pin);
    expect(usePlacesStore.getState().favorites).toEqual([]);
    usePlacesStore.getState().clearRecents();
    expect(usePlacesStore.getState().recents).toEqual([]);
  });
});

describe("plan store", () => {
  it("clears the selected route when an endpoint changes", () => {
    const plan = usePlanStore.getState();
    plan.selectRoute("r1");
    plan.setDestination({ id: "d", name: "Destino", location: [1, 1] });
    expect(usePlanStore.getState().selectedRouteId).toBeNull();
  });

  it("swaps endpoints, using the current position as the implicit origin", () => {
    const plan = usePlanStore.getState();
    plan.swap("Aquí");
    expect(usePlanStore.getState().origin).toBeNull();
    plan.setPosition([0.5, 0.5]);
    plan.setDestination({ id: "d", name: "Destino", location: [1, 1] });
    plan.swap("Aquí");
    expect(usePlanStore.getState().origin?.id).toBe("d");
    expect(usePlanStore.getState().destination).toEqual({ id: "pin:current", name: "Aquí", location: [0.5, 0.5] });
  });

  it("starts and stops navigation", () => {
    usePlanStore.getState().startNavigation(route);
    expect(usePlanStore.getState().activeRoute?.id).toBe("r1");
    usePlanStore.getState().stopNavigation();
    expect(usePlanStore.getState().activeRoute).toBeNull();
  });
});
