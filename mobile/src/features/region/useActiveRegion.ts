// Resolves the active region and mirrors it into useRegionStore. Nothing here assumes a
// particular campus: the list always comes from GET /v1/regions.
import type { Region } from "@reduc/api-client";
import { useEffect } from "react";

import { useRegions } from "../../lib/api";
import { geometryContains, type LonLat } from "../../lib/geo";
import { usePlanStore } from "../../stores/plan";
import { useRegionStore } from "../../stores/region";
import { useSettingsStore } from "../../stores/settings";

export function pickRegion(regions: readonly Region[], manualSlug: string | null, position: LonLat | null): Region | null {
  if (manualSlug !== null) {
    const chosen = regions.find((region) => region.slug === manualSlug);
    if (chosen) {
      return chosen;
    }
  }
  if (position !== null) {
    const containing = regions.find((region) => geometryContains(region.boundary, position));
    if (containing) {
      return containing;
    }
  }
  // Outside every region (or position unknown): show the first one so the map is not empty.
  return regions[0] ?? null;
}

/** Mount once near the root; screens read the result from useRegionStore. */
export function useActiveRegionSync(): { isLoading: boolean; isError: boolean; refetch: () => void } {
  const regions = useRegions();
  const manualSlug = useSettingsStore((state) => state.regionSlug);
  const position = usePlanStore((state) => state.position);
  const current = useRegionStore((state) => state.region);
  const setRegion = useRegionStore((state) => state.setRegion);
  const demoLocation = useSettingsStore((state) => state.demoLocation);

  const data = regions.data;
  // In demo mode the position is derived from the region, so it must not drive the choice.
  const next = data ? pickRegion(data, manualSlug, demoLocation ? null : position) : null;
  const nextKey = next ? `${next.id}:${next.map_version.number}` : null;
  const currentKey = current ? `${current.id}:${current.map_version.number}` : null;

  useEffect(() => {
    if (data && nextKey !== currentKey) {
      setRegion(next);
    }
    // `next` is derived from the keys compared above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, nextKey, currentKey, setRegion]);

  return { isLoading: regions.isLoading, isError: regions.isError, refetch: () => void regions.refetch() };
}
