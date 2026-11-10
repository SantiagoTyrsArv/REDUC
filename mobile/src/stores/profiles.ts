// Mobility profiles live only on the device (ADR-007) and travel with each route request.
import type { MobilityProfile } from "@reduc/api-client";
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import { appStorage } from "../lib/storage";

export interface StoredProfile {
  id: string;
  name: string;
  profile: MobilityProfile;
}

interface ProfileState {
  profiles: StoredProfile[];
  activeProfileId: string | null;
  addProfile: (name: string, profile: MobilityProfile) => string;
  updateProfile: (id: string, changes: { name?: string; profile?: MobilityProfile }) => void;
  removeProfile: (id: string) => void;
  setActive: (id: string) => void;
}

function newId(): string {
  return `p-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export const useProfileStore = create<ProfileState>()(
  persist(
    (set) => ({
      profiles: [],
      activeProfileId: null,
      addProfile: (name, profile) => {
        const id = newId();
        set((state) => ({
          profiles: [...state.profiles, { id, name, profile }],
          activeProfileId: state.activeProfileId ?? id,
        }));
        return id;
      },
      updateProfile: (id, changes) =>
        set((state) => ({
          profiles: state.profiles.map((item) =>
            item.id === id
              ? { ...item, name: changes.name ?? item.name, profile: changes.profile ?? item.profile }
              : item,
          ),
        })),
      removeProfile: (id) =>
        set((state) => {
          const profiles = state.profiles.filter((item) => item.id !== id);
          const activeProfileId = state.activeProfileId === id ? (profiles[0]?.id ?? null) : state.activeProfileId;
          return { profiles, activeProfileId };
        }),
      setActive: (id) => set({ activeProfileId: id }),
    }),
    { name: "profiles", storage: createJSONStorage(() => appStorage) },
  ),
);

export function selectActiveProfile(state: ProfileState): StoredProfile | null {
  return state.profiles.find((item) => item.id === state.activeProfileId) ?? state.profiles[0] ?? null;
}
