// Region the app is working with: detected from the position or chosen by hand (docs/07 §3).
import type { Region } from "@reduc/api-client";
import { create } from "zustand";

interface RegionState {
  region: Region | null;
  setRegion: (region: Region | null) => void;
}

export const useRegionStore = create<RegionState>()((set) => ({
  region: null,
  setRegion: (region) => set({ region }),
}));
