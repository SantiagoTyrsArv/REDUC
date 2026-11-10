// Human-readable distances and durations in the user's units.
import type { Units } from "../stores/settings";

export function formatDistance(meters: number, units: Units): string {
  if (units === "imperial") {
    const feet = meters * 3.28084;
    return feet < 1000 ? `${Math.round(feet / 10) * 10 || Math.round(feet)} ft` : `${(meters / 1609.344).toFixed(1)} mi`;
  }
  if (meters < 1000) {
    return `${Math.round(meters)} m`;
  }
  return `${(meters / 1000).toFixed(1)} km`;
}

/** Minutes, rounded up so the estimate never under-promises. */
export function durationMinutes(seconds: number): number {
  return Math.max(1, Math.ceil(seconds / 60));
}
