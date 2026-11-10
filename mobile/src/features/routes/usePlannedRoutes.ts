// The route request derived from the stores, shared by /route and /route/segments so both
// screens read the same React Query cache entry (docs/07 §3).
import type { Route } from "@reduc/api-client";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { useRoutes, type RoutePlanResult, type RouteQuery } from "../../lib/api";
import { usePlanStore } from "../../stores/plan";
import { selectActiveProfile, useProfileStore } from "../../stores/profiles";

export interface PlannedRoutes {
  query: RouteQuery | null;
  result: RoutePlanResult | undefined;
  /** Routes that can be shown: the accessible ones, or the fallback when there is none. */
  routes: Route[];
  selected: Route | null;
  isFallback: boolean;
  isLoading: boolean;
  error: Error | null;
  refetch: () => void;
}

export function usePlannedRoutes(): PlannedRoutes {
  const { i18n } = useTranslation();
  const origin = usePlanStore((state) => state.origin);
  const destination = usePlanStore((state) => state.destination);
  const position = usePlanStore((state) => state.position);
  const selectedRouteId = usePlanStore((state) => state.selectedRouteId);
  const active = useProfileStore(selectActiveProfile);

  const originPoint = origin?.location ?? position;
  const locale = i18n.language === "en" ? "en" : "es";
  // The key rounds the origin to 5 m, so small GPS jitter does not refetch.
  const query = useMemo<RouteQuery | null>(
    () =>
      originPoint && destination && active
        ? { origin: originPoint, destination: destination.location, profile: active.profile, locale }
        : null,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [originPoint?.[0], originPoint?.[1], destination, active, locale],
  );
  const response = useRoutes(query);
  const result = response.data;

  const fallback = result?.kind === "no_accessible_route" ? result.error.extra.fallback_route : null;
  const routes = useMemo<Route[]>(
    () => (result?.kind === "ok" ? result.data.routes : fallback ? [fallback] : []),
    [result, fallback],
  );
  const selected = routes.find((route) => route.id === selectedRouteId) ?? routes[0] ?? null;

  return {
    query,
    result,
    routes,
    selected,
    isFallback: result?.kind === "no_accessible_route",
    isLoading: query !== null && response.isPending,
    error: response.error,
    refetch: () => void response.refetch(),
  };
}
