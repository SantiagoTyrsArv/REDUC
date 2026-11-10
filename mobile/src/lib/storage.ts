// Persistence for zustand stores, backed by MMKV (docs/07 §3). MMKV ships a web
// implementation over localStorage and a mock for Jest, so one adapter serves all targets.
import { createMMKV, type MMKV } from "react-native-mmkv";
import type { StateStorage } from "zustand/middleware";

const memory = new Map<string, string>();
let instance: MMKV | null | undefined;

function mmkv(): MMKV | null {
  if (instance === undefined) {
    try {
      instance = createMMKV({ id: "reduc" });
    } catch {
      // Private browsing or a missing native module: keep working without persistence.
      instance = null;
    }
  }
  return instance;
}

export const appStorage: StateStorage = {
  getItem: (name) => mmkv()?.getString(name) ?? memory.get(name) ?? null,
  setItem: (name, value) => {
    const store = mmkv();
    if (store) {
      store.set(name, value);
    } else {
      memory.set(name, value);
    }
  },
  removeItem: (name) => {
    mmkv()?.remove(name);
    memory.delete(name);
  },
};
