// Thin entry point over the generated schema. Everything in schema.d.ts is produced by
// `pnpm gen:api`; do not edit that file by hand.
import createClient, { type Client } from "openapi-fetch";

import type { components, paths } from "./schema";

export type { components, paths };
export type Schemas = components["schemas"];

export type ApiError = Schemas["ErrorOut"];
export type Barrier = Schemas["BarrierOut"];
export type BlockingBarrier = Schemas["BlockingBarrierOut"];
export type Instruction = Schemas["InstructionOut"];
export type MobilityProfile = Schemas["ProfileModel"];
export type NoAccessibleRouteError = Schemas["NoAccessibleRouteError"];
export type NoAccessibleRouteExtra = Schemas["NoAccessibleRouteExtra"];
export type Poi = Schemas["PoiOut"];
export type Preset = Schemas["PresetOut"];
export type Region = Schemas["RegionOut"];
export type Route = Schemas["RouteOut"];
export type RouteRequest = Schemas["RouteRequest"];
export type RoutesResponse = Schemas["RoutesResponse"];
export type Segment = Schemas["SegmentOut"];
export type Shortest = Schemas["ShortestOut"];
export type RouteWarning = Schemas["WarningOut"];

export type ApiClient = Client<paths>;

export function createApiClient(baseUrl: string, getToken?: () => string | null): ApiClient {
  // Resolve `fetch` on every call so polyfills and test doubles installed later are honoured.
  const client = createClient<paths>({ baseUrl, fetch: (request) => globalThis.fetch(request) });
  if (getToken) {
    client.use({
      onRequest({ request }) {
        const token = getToken();
        if (token) {
          request.headers.set("Authorization", `Bearer ${token}`);
        }
        return request;
      },
    });
  }
  return client;
}
