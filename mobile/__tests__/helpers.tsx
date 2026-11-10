// Fixtures and helpers for screen tests. API responses are served by a fake `fetch`.
import type { MobilityProfile, Region, Route } from "@reduc/api-client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react-native";
import type { ReactElement } from "react";

import { usePlacesStore } from "../src/stores/places";
import { usePlanStore } from "../src/stores/plan";
import { useProfileStore } from "../src/stores/profiles";
import { useRegionStore } from "../src/stores/region";
import { useSettingsStore } from "../src/stores/settings";

export const router = (globalThis as Record<string, unknown>).__router as Record<
  "push" | "replace" | "back" | "dismissTo",
  jest.Mock
>;
export const setRouteParams = (globalThis as Record<string, unknown>).__setRouteParams as (
  params: Record<string, string>,
) => void;

export const manualProfile: MobilityProfile = {
  device: "manual",
  max_uphill_pct: 6,
  max_downhill_pct: 8,
  max_cross_slope_pct: 3,
  max_step_cm: 2,
  min_width_m: 0.9,
  max_surface_class: 2,
  require_curb_ramps: true,
  avoid_unverified: false,
  speed_mps: 0.9,
  weights: { slope: 1, surface: 1, uncertainty: 1 },
};

export const presets = [
  { id: "manual", profile: manualProfile },
  { id: "electric", profile: { ...manualProfile, device: "electric", max_uphill_pct: 12, max_step_cm: 5 } },
];

export const region: Region = {
  id: "11111111-1111-1111-1111-111111111111",
  slug: "zona-prueba",
  name: "Zona de prueba",
  bbox: [0, 0, 0.002, 0.002],
  boundary: {
    type: "MultiPolygon",
    coordinates: [
      [
        [
          [0, 0],
          [0.002, 0],
          [0.002, 0.002],
          [0, 0.002],
          [0, 0],
        ],
      ],
    ],
  },
  map_version: { id: "22222222-2222-2222-2222-222222222222", number: 3, published_at: "2026-11-01T00:00:00Z" },
  stats: { edges: 60, coverage_pct: 80, verified_pct: 55 },
};

/** A 200 m L-shaped route: 100 m east (accessible), then 100 m north (caution, with a warning). */
export const route: Route = {
  id: "r1",
  distance_m: 200,
  duration_s: 240,
  accessibility_score: 82,
  max_slope_pct: 4.5,
  verified_pct: 90,
  caution_segments: 1,
  geometry: {
    type: "LineString",
    coordinates: [
      [0, 0],
      [0.0009, 0],
      [0.0009, 0.0009],
    ],
  },
  segments: [
    {
      distance_m: 100,
      edge_ids: [1, 2],
      geometry: {
        type: "LineString",
        coordinates: [
          [0, 0],
          [0.0009, 0],
        ],
      },
      slope_pct: 0.5,
      status: "accessible",
      surface_class: 0,
      warnings: [],
    },
    {
      distance_m: 100,
      edge_ids: [3, 4],
      geometry: {
        type: "LineString",
        coordinates: [
          [0.0009, 0],
          [0.0009, 0.0009],
        ],
      },
      slope_pct: 4.5,
      status: "caution",
      surface_class: 1,
      warnings: [{ code: "slope_moderate", severity: "minor", message: "Pendiente de subida del 4,5 % durante 100 m" }],
    },
  ],
  instructions: [
    { maneuver: "depart", text: "Sal hacia el este y continúa 100 m", distance_m: 100, location: [0, 0] },
    { maneuver: "left", text: "Gira a la izquierda y continúa 100 m", distance_m: 100, location: [0.0009, 0] },
    { maneuver: "arrive", text: "Has llegado a tu destino", distance_m: 0, location: [0.0009, 0.0009] },
  ],
};

export const alternative: Route = { ...route, id: "r2", distance_m: 260, duration_s: 300, accessibility_score: 74 };

export const blockingBarrier = {
  id: "33333333-3333-3333-3333-333333333333",
  class: "stairs",
  location: [0.0004, 0.0004] as [number, number],
  message: "Escalera de 8 escalones",
};

export const routesResponse = {
  region: region.slug,
  map_version: 3,
  routes: [route, alternative],
  shortest: { distance_m: 150, blocking_barriers: [blockingBarrier] },
};

export function noRouteResponse(fallback: Route | null) {
  return {
    type: "no_accessible_route",
    title: "No existe una ruta accesible",
    status: 422,
    detail: "Ninguna ruta cumple tu perfil",
    extra: {
      region: region.slug,
      map_version: 3,
      violated_constraints: fallback ? ["slope"] : [],
      fallback_route: fallback,
      shortest: { distance_m: 150, blocking_barriers: [blockingBarrier] },
    },
  };
}

type Handler = { status?: number; body: unknown } | ((url: string, init?: RequestInit) => { status?: number; body: unknown });

/** Install a fake `fetch` that answers by URL substring. Returns the list of requested URLs. */
export function mockApi(handlers: Record<string, Handler>): { calls: { url: string; body: unknown }[] } {
  const calls: { url: string; body: unknown }[] = [];
  globalThis.fetch = jest.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : null;
    const url = request ? request.url : String(input);
    const rawBody = request ? await request.clone().text() : typeof init?.body === "string" ? init.body : "";
    calls.push({ url, body: rawBody ? JSON.parse(rawBody) : null });
    const key = Object.keys(handlers).find((fragment) => url.includes(fragment));
    if (key === undefined) {
      throw new TypeError(`Unexpected request in test: ${url}`);
    }
    const handler = handlers[key]!;
    const { status = 200, body } = typeof handler === "function" ? handler(url, init) : handler;
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  }) as unknown as typeof fetch;
  return { calls };
}

export function resetStores(): void {
  useSettingsStore.setState({
    language: "es",
    units: "metric",
    onboardingDone: true,
    regionSlug: null,
    showAccessibilityLayer: true,
    demoLocation: false,
  });
  useProfileStore.setState({ profiles: [{ id: "p1", name: "Mi silla", profile: manualProfile }], activeProfileId: "p1" });
  usePlacesStore.setState({ favorites: [], recents: [] });
  usePlanStore.setState({
    origin: null,
    destination: null,
    pickTarget: null,
    selectedRouteId: null,
    activeRoute: null,
    position: null,
  });
  useRegionStore.setState({ region });
}

export async function renderScreen(element: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  return render(<QueryClientProvider client={client}>{element}</QueryClientProvider>);
}
