// Destination / origin search (RF-11): POIs of the region, favourites, recents and map pick.
import type { Poi } from "@reduc/api-client";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { StyleSheet, TextInput, View } from "react-native";

import { IconButton, ListRow } from "../src/components/rows";
import { AppButton, AppText, Loading, Notice, Screen, SectionTitle } from "../src/components/ui";
import { usePois } from "../src/lib/api";
import type { LonLat } from "../src/lib/geo";
import { usePlacesStore, type Place } from "../src/stores/places";
import { usePlanStore, type PickTarget } from "../src/stores/plan";
import { useRegionStore } from "../src/stores/region";
import { radius, spacing, TOUCH_TARGET, useTheme } from "../src/theme";

const KNOWN_CATEGORIES = ["building", "entrance", "toilet", "parking", "service"] as const;

function useDebounced(value: string, delayMs: number): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

function poiToPlace(poi: Poi): Place {
  return { id: poi.id, name: poi.name, location: poi.location as LonLat, category: poi.category };
}

export default function SearchScreen() {
  const { t } = useTranslation();
  const router = useRouter();
  const { colors } = useTheme();
  const params = useLocalSearchParams<{ target?: string }>();
  const target: PickTarget = params.target === "origin" ? "origin" : "destination";
  const region = useRegionStore((state) => state.region);
  const favorites = usePlacesStore((state) => state.favorites);
  const recents = usePlacesStore((state) => state.recents);
  const toggleFavorite = usePlacesStore((state) => state.toggleFavorite);
  const clearRecents = usePlacesStore((state) => state.clearRecents);
  const [text, setText] = useState("");
  const query = useDebounced(text, 250);
  const pois = usePois(region?.slug, query);

  const categoryLabel = (category: string | undefined): string | undefined => {
    if (category === undefined) {
      return undefined;
    }
    const known = (KNOWN_CATEGORIES as readonly string[]).includes(category) ? category : "other";
    return t(`search.category.${known as (typeof KNOWN_CATEGORIES)[number] | "other"}`);
  };

  const choose = (place: Place | null) => {
    const plan = usePlanStore.getState();
    if (target === "origin") {
      plan.setOrigin(place);
    } else if (place) {
      plan.setDestination(place);
    }
    if (place) {
      usePlacesStore.getState().addRecent(place);
    }
    router.replace("/route");
  };

  const pickOnMap = () => {
    usePlanStore.getState().setPickTarget(target);
    router.dismissTo("/");
  };

  const star = (place: Place) => {
    const isFavorite = favorites.some((item) => item.id === place.id);
    return (
      <IconButton
        symbol={isFavorite ? "★" : "☆"}
        selected={isFavorite}
        accessibilityLabel={t(isFavorite ? "search.removeFavorite" : "search.addFavorite", { name: place.name })}
        onPress={() => toggleFavorite(place)}
      />
    );
  };

  const placeRow = (place: Place, prefix: string, extra?: string) => (
    <ListRow
      key={`${prefix}-${place.id}`}
      testID={`${prefix}-${place.id}`}
      title={place.name}
      subtitle={[categoryLabel(place.category), extra].filter(Boolean).join(" · ") || undefined}
      hint={t("search.selectHint")}
      onPress={() => choose(place)}
      right={star(place)}
    />
  );

  return (
    <Screen scroll>
      <AppText variant="heading" accessibilityRole="header">
        {target === "origin" ? t("search.forOrigin") : t("search.forDestination")}
      </AppText>
      <TextInput
        testID="search-input"
        value={text}
        onChangeText={setText}
        placeholder={t("search.placeholder")}
        placeholderTextColor={colors.textMuted}
        accessibilityLabel={t("search.inputLabel")}
        accessibilityHint={t("search.inputHint")}
        autoCorrect={false}
        returnKeyType="search"
        allowFontScaling
        maxFontSizeMultiplier={2}
        style={[styles.input, { color: colors.text, borderColor: colors.border, backgroundColor: colors.surface }]}
      />

      {target === "origin" ? (
        <AppButton
          testID="search-current"
          variant="secondary"
          label={t("search.useCurrent")}
          hint={t("search.useCurrentHint")}
          onPress={() => choose(null)}
        />
      ) : null}
      <AppButton
        testID="search-pick-map"
        variant="secondary"
        label={t("search.pickOnMap")}
        hint={t("search.pickOnMapHint")}
        onPress={pickOnMap}
      />

      {query.trim() === "" && favorites.length > 0 ? (
        <View style={styles.section}>
          <SectionTitle>{t("search.favorites")}</SectionTitle>
          {favorites.map((place) => placeRow(place, "favorite"))}
        </View>
      ) : null}

      {query.trim() === "" && recents.length > 0 ? (
        <View style={styles.section}>
          <SectionTitle>{t("search.recents")}</SectionTitle>
          {recents.map((place) => placeRow(place, "recent"))}
          <AppButton variant="secondary" label={t("search.clearRecents")} onPress={clearRecents} />
        </View>
      ) : null}

      <View style={styles.section}>
        <SectionTitle>{t("search.results")}</SectionTitle>
        {region === null ? <Notice tone="info" title={t("errors.noRegion")} body={t("errors.noRegionHint")} /> : null}
        {region !== null && pois.isPending ? <Loading label={t("common.loading")} /> : null}
        {pois.isError ? (
          <Notice tone="error" title={t("errors.title")} body={t("errors.network")}>
            <AppButton label={t("common.retry")} onPress={() => void pois.refetch()} />
          </Notice>
        ) : null}
        {pois.data?.length === 0 ? (
          <AppText muted accessibilityLiveRegion="polite">
            {t("search.empty")}
          </AppText>
        ) : null}
        {pois.data?.map((poi) =>
          placeRow(
            poiToPlace(poi),
            "poi",
            poi.accessible_entrance ? t("search.accessibleEntrance") : t("search.noAccessibleEntrance"),
          ),
        )}
      </View>
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
  section: { gap: spacing.sm },
});
