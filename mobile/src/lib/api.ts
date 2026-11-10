// Remote data: the generated client plus React Query hooks.
import {
  createApiClient,
  type ApiError,
  type Barrier,
  type MobilityProfile,
  type NoAccessibleRouteError,
  type Poi,
  type Preset,
  type Region,
  type RoutesResponse,
} from "@reduc/api-client";
import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { config } from "./config";
import { roundToGrid, type LonLat } from "./geo";

export const api = createApiClient(config.apiUrl);

/** Error returned by the API in the uniform format of docs/04 §1. */
export class ApiProblem extends Error {
  readonly type: string;
  readonly status: number;
  readonly extra: Record<string, unknown> | null;

  constructor(body: Partial<ApiError> | undefined, status: number) {
    super(body?.detail ?? body?.title ?? "network_error");
    this.type = body?.type ?? "network_error";
    this.status = status;
    this.extra = (body?.extra as Record<string, unknown> | null | undefined) ?? null;
  }
}

function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.data === undefined) {
    throw new ApiProblem(result.error as Partial<ApiError> | undefined, result.response.status);
  }
  return result.data;
}

export function useRegions(): UseQueryResult<Region[], Error> {
  return useQuery({
    queryKey: ["regions"],
    queryFn: async () => unwrap(await api.GET("/v1/regions")),
    staleTime: 10 * 60_000,
  });
}

export function usePresets(): UseQueryResult<Preset[], Error> {
  return useQuery({
    queryKey: ["presets"],
    queryFn: async () => unwrap(await api.GET("/v1/profiles/presets")),
    staleTime: 60 * 60_000,
  });
}

export function usePois(slug: string | undefined, query: string): UseQueryResult<Poi[], Error> {
  const q = query.trim();
  return useQuery({
    queryKey: ["pois", slug, q],
    enabled: slug !== undefined,
    queryFn: async () =>
      unwrap(
        await api.GET("/v1/regions/{slug}/pois", {
          params: { path: { slug: slug! }, query: q ? { q, limit: 30 } : { limit: 30 } },
        }),
      ),
    staleTime: 5 * 60_000,
  });
}

export function useBarrier(id: string | undefined, locale: string): UseQueryResult<Barrier, Error> {
  return useQuery({
    queryKey: ["barrier", id, locale],
    enabled: id !== undefined,
    queryFn: async () =>
      unwrap(await api.GET("/v1/barriers/{barrier_id}", { params: { path: { barrier_id: id! }, query: { locale } } })),
  });
}

export type RoutePlanResult =
  | { kind: "ok"; data: RoutesResponse }
  | { kind: "no_accessible_route"; error: NoAccessibleRouteError };

export interface RouteQuery {
  origin: LonLat;
  destination: LonLat;
  profile: MobilityProfile;
  locale: string;
}

export async function fetchRoutes(query: RouteQuery): Promise<RoutePlanResult> {
  const result = await api.POST("/v1/routes", {
    body: {
      origin: query.origin,
      destination: query.destination,
      profile: query.profile,
      alternatives: 2,
      include_shortest: true,
      locale: query.locale,
    },
  });
  if (result.data !== undefined) {
    return { kind: "ok", data: result.data };
  }
  const body = result.error as Partial<ApiError> | undefined;
  if (body?.type === "no_accessible_route") {
    return { kind: "no_accessible_route", error: body as NoAccessibleRouteError };
  }
  throw new ApiProblem(body, result.response.status);
}

/** Cache key of docs/07 §3: origin rounded to 5 m, destination and a profile hash. */
export function routeQueryKey(query: RouteQuery | null): readonly unknown[] {
  if (query === null) {
    return ["routes", "idle"];
  }
  return [
    "routes",
    roundToGrid(query.origin).join(","),
    query.destination.join(","),
    JSON.stringify(query.profile),
    query.locale,
  ];
}

export function useRoutes(query: RouteQuery | null): UseQueryResult<RoutePlanResult, Error> {
  return useQuery({
    queryKey: routeQueryKey(query),
    enabled: query !== null,
    queryFn: () => fetchRoutes(query!),
    staleTime: 5 * 60_000,
    retry: (count, error) => !(error instanceof ApiProblem && error.status < 500) && count < 2,
  });
}
