// The trip being planned. Not persisted: routes are only cached by React Query (docs/07 §3).
import type { Route } from "@reduc/api-client";
import { create } from "zustand";

import type { LonLat } from "../lib/geo";
import type { Place } from "./places";

export type PickTarget = "origin" | "destination";

interface PlanState {
  /** null = start from the user's current position. */
  origin: Place | null;
  destination: Place | null;
  /** When set, the next tap on the main map chooses this endpoint. */
  pickTarget: PickTarget | null;
  selectedRouteId: string | null;
  /** Route being followed in /navigate. */
  activeRoute: Route | null;
  /** Live position reported by the location provider. */
  position: LonLat | null;
  setOrigin: (place: Place | null) => void;
  setDestination: (place: Place | null) => void;
  setPickTarget: (target: PickTarget | null) => void;
  selectRoute: (id: string | null) => void;
  startNavigation: (route: Route) => void;
  stopNavigation: () => void;
  setPosition: (position: LonLat | null) => void;
  swap: (currentLocationName: string) => void;
}

export const usePlanStore = create<PlanState>()((set) => ({
  origin: null,
  destination: null,
  pickTarget: null,
  selectedRouteId: null,
  activeRoute: null,
  position: null,
  setOrigin: (origin) => set({ origin, selectedRouteId: null }),
  setDestination: (destination) => set({ destination, selectedRouteId: null }),
  setPickTarget: (pickTarget) => set({ pickTarget }),
  selectRoute: (selectedRouteId) => set({ selectedRouteId }),
  startNavigation: (activeRoute) => set({ activeRoute }),
  stopNavigation: () => set({ activeRoute: null }),
  setPosition: (position) => set({ position }),
  swap: (currentLocationName) =>
    set((state) => {
      if (state.destination === null) {
        return state;
      }
      const origin = state.destination;
      const destination =
        state.origin ??
        (state.position ? { id: "pin:current", name: currentLocationName, location: state.position } : null);
      return { origin, destination, selectedRouteId: null };
    }),
}));
