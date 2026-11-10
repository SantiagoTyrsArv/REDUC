import { create } from "zustand";

export type LocationPermission = "unknown" | "granted" | "denied";

interface LocationState {
  permission: LocationPermission;
  setPermission: (permission: LocationPermission) => void;
}

export const useLocationStore = create<LocationState>()((set) => ({
  permission: "unknown",
  setPermission: (permission) => set({ permission }),
}));
