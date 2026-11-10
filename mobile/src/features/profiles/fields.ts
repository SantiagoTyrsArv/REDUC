// Editable parameters of a mobility profile. Ranges mirror the API validation (ProfileModel).
import type { MobilityProfile } from "@reduc/api-client";

export type NumericFieldKey =
  | "max_uphill_pct"
  | "max_downhill_pct"
  | "max_cross_slope_pct"
  | "max_step_cm"
  | "min_width_m"
  | "max_surface_class"
  | "speed_mps"
  | "weight_slope"
  | "weight_surface"
  | "weight_uncertainty";

export interface NumericField {
  key: NumericFieldKey;
  min: number;
  max: number;
  step: number;
  decimals: number;
  group: "limits" | "preferences";
}

export const NUMERIC_FIELDS: readonly NumericField[] = [
  { key: "max_uphill_pct", min: 1, max: 20, step: 0.5, decimals: 1, group: "limits" },
  { key: "max_downhill_pct", min: 1, max: 20, step: 0.5, decimals: 1, group: "limits" },
  { key: "max_cross_slope_pct", min: 1, max: 10, step: 0.5, decimals: 1, group: "limits" },
  { key: "max_step_cm", min: 0, max: 15, step: 0.5, decimals: 1, group: "limits" },
  { key: "min_width_m", min: 0.6, max: 1.5, step: 0.05, decimals: 2, group: "limits" },
  { key: "max_surface_class", min: 0, max: 4, step: 1, decimals: 0, group: "limits" },
  { key: "speed_mps", min: 0.3, max: 3, step: 0.1, decimals: 1, group: "preferences" },
  { key: "weight_slope", min: 0, max: 3, step: 0.25, decimals: 2, group: "preferences" },
  { key: "weight_surface", min: 0, max: 3, step: 0.25, decimals: 2, group: "preferences" },
  { key: "weight_uncertainty", min: 0, max: 3, step: 0.25, decimals: 2, group: "preferences" },
];

export type BooleanFieldKey = "require_curb_ramps" | "avoid_unverified";
export const BOOLEAN_FIELDS: readonly BooleanFieldKey[] = ["require_curb_ramps", "avoid_unverified"];

const WEIGHT_KEYS = { weight_slope: "slope", weight_surface: "surface", weight_uncertainty: "uncertainty" } as const;

function isWeight(key: NumericFieldKey): key is keyof typeof WEIGHT_KEYS {
  return key in WEIGHT_KEYS;
}

export function getNumeric(profile: MobilityProfile, key: NumericFieldKey): number {
  if (isWeight(key)) {
    return profile.weights?.[WEIGHT_KEYS[key]] ?? 1;
  }
  return profile[key];
}

/** Clamp to the field range and snap to its step, avoiding floating point residue. */
export function normalize(field: NumericField, value: number): number {
  const clamped = Math.min(field.max, Math.max(field.min, value));
  const snapped = field.min + Math.round((clamped - field.min) / field.step) * field.step;
  return Number(Math.min(field.max, snapped).toFixed(field.decimals));
}

export function setNumeric(profile: MobilityProfile, field: NumericField, value: number): MobilityProfile {
  const next = normalize(field, value);
  if (isWeight(field.key)) {
    const weights = { slope: 1, surface: 1, uncertainty: 1, ...profile.weights };
    return { ...profile, weights: { ...weights, [WEIGHT_KEYS[field.key]]: next } };
  }
  return { ...profile, [field.key]: next };
}

export function formatNumber(value: number, decimals: number, language: string): string {
  return new Intl.NumberFormat(language, { maximumFractionDigits: decimals }).format(value);
}
