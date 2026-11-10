// Feeds the live position into the plan store. The position never leaves the device except
// as the origin of a route request (RNF-07).
import * as Location from "expo-location";
import { useEffect } from "react";

import { boundsCenter, type LonLat } from "../../lib/geo";
import { usePlanStore } from "../../stores/plan";
import { useRegionStore } from "../../stores/region";
import { useSettingsStore } from "../../stores/settings";
import { useLocationStore } from "./store";

/** Ask the system for foreground location access. Safe to call repeatedly. */
export async function requestLocationPermission(): Promise<boolean> {
  try {
    const result = await Location.requestForegroundPermissionsAsync();
    const granted = result.status === Location.PermissionStatus.GRANTED;
    useLocationStore.getState().setPermission(granted ? "granted" : "denied");
    return granted;
  } catch {
    useLocationStore.getState().setPermission("denied");
    return false;
  }
}

/** Mount once near the root. Watches the position while permission is granted. */
export function useLocationWatcher(): void {
  const demoLocation = useSettingsStore((state) => state.demoLocation);
  const permission = useLocationStore((state) => state.permission);
  const region = useRegionStore((state) => state.region);
  const navigating = usePlanStore((state) => state.activeRoute !== null);

  // Learn the current permission without prompting; the prompt belongs to onboarding.
  useEffect(() => {
    let cancelled = false;
    Location.getForegroundPermissionsAsync()
      .then((result) => {
        if (!cancelled && result.status === Location.PermissionStatus.GRANTED) {
          useLocationStore.getState().setPermission("granted");
        } else if (!cancelled && !result.canAskAgain) {
          useLocationStore.getState().setPermission("denied");
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  // Demo mode: stand in the middle of the active region. The navigation screen moves the
  // position itself while a simulated trip is running.
  useEffect(() => {
    if (demoLocation && region && !navigating) {
      const center: LonLat = boundsCenter(region.bbox);
      usePlanStore.getState().setPosition(center);
    }
  }, [demoLocation, region, navigating]);

  useEffect(() => {
    if (demoLocation || permission !== "granted") {
      return undefined;
    }
    let subscription: Location.LocationSubscription | null = null;
    let cancelled = false;
    Location.watchPositionAsync(
      { accuracy: Location.Accuracy.High, distanceInterval: 2, timeInterval: 1000 },
      (update) => {
        usePlanStore.getState().setPosition([update.coords.longitude, update.coords.latitude]);
      },
    )
      .then((created) => {
        if (cancelled) {
          created.remove();
        } else {
          subscription = created;
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
      subscription?.remove();
    };
  }, [demoLocation, permission]);
}
