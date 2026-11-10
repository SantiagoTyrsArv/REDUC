// Favourites and recent destinations, stored locally (RF-11).
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import type { LonLat } from "../lib/geo";
import { appStorage } from "../lib/storage";

export const MAX_RECENTS = 20;

export interface Place {
  /** POI id, or a synthetic key for map picks. */
  id: string;
  name: string;
  location: LonLat;
  category?: string;
}

interface PlacesState {
  favorites: Place[];
  recents: Place[];
  toggleFavorite: (place: Place) => void;
  addRecent: (place: Place) => void;
  clearRecents: () => void;
}

export const usePlacesStore = create<PlacesState>()(
  persist(
    (set) => ({
      favorites: [],
      recents: [],
      toggleFavorite: (place) =>
        set((state) => ({
          favorites: state.favorites.some((item) => item.id === place.id)
            ? state.favorites.filter((item) => item.id !== place.id)
            : [place, ...state.favorites],
        })),
      addRecent: (place) =>
        set((state) => ({
          recents: [place, ...state.recents.filter((item) => item.id !== place.id)].slice(0, MAX_RECENTS),
        })),
      clearRecents: () => set({ recents: [] }),
    }),
    { name: "places", storage: createJSONStorage(() => appStorage) },
  ),
);

export function placeFromPoint(location: LonLat, name: string): Place {
  return { id: `pin:${location[0].toFixed(5)},${location[1].toFixed(5)}`, name, location };
}
