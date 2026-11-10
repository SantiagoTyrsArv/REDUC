// Pure turn-by-turn logic: where the user is along the route and what comes next.
import type { Instruction, Route, RouteWarning } from "@reduc/api-client";

import { projectOnLine, type LonLat } from "../../lib/geo";

/** A deviation larger than this triggers a recalculation (RF-10). */
export const OFF_ROUTE_THRESHOLD_M = 25;
/** The trip is finished when the user is this close to the end. */
export const ARRIVAL_THRESHOLD_M = 8;
/** Warnings are announced when they start within this distance. */
export const WARNING_LOOKAHEAD_M = 40;

export interface UpcomingWarning {
  warning: RouteWarning;
  /** Meters until the segment starts; 0 when the user is already on it. */
  distanceM: number;
}

export interface NavigationProgress {
  distanceAlongM: number;
  remainingM: number;
  remainingS: number;
  offRouteM: number;
  isOffRoute: boolean;
  hasArrived: boolean;
  /** Index of the instruction being followed right now. */
  currentIndex: number;
  /** The maneuver the user has to perform next, if any. */
  next: Instruction | null;
  distanceToNextM: number;
  upcomingWarning: UpcomingWarning | null;
}

/** Distance from the start at which each instruction's maneuver happens. */
export function maneuverOffsets(instructions: readonly Instruction[]): number[] {
  const offsets: number[] = [];
  let walked = 0;
  for (const instruction of instructions) {
    offsets.push(walked);
    walked += instruction.distance_m;
  }
  return offsets;
}

export function computeProgress(route: Route, position: LonLat): NavigationProgress | null {
  const projection = projectOnLine(route.geometry.coordinates as LonLat[], position);
  if (projection === null) {
    return null;
  }
  const total = route.distance_m;
  const along = Math.min(projection.distanceAlongM, total);
  const remainingM = Math.max(0, total - along);
  const offsets = maneuverOffsets(route.instructions);

  let currentIndex = 0;
  for (let i = 0; i < offsets.length; i += 1) {
    if (offsets[i]! <= along + 0.5) {
      currentIndex = i;
    }
  }
  const nextIndex = route.instructions.findIndex((_, i) => i > currentIndex);
  const next = nextIndex >= 0 ? route.instructions[nextIndex]! : null;
  const distanceToNextM = nextIndex >= 0 ? Math.max(0, offsets[nextIndex]! - along) : remainingM;

  let upcomingWarning: UpcomingWarning | null = null;
  let segmentStart = 0;
  for (const segment of route.segments) {
    const segmentEnd = segmentStart + segment.distance_m;
    const ahead = segmentStart - along;
    const onSegment = along >= segmentStart && along < segmentEnd;
    if ((onSegment || (ahead > 0 && ahead <= WARNING_LOOKAHEAD_M)) && segment.warnings.length > 0) {
      const major = segment.warnings.find((warning) => warning.severity === "major");
      upcomingWarning = { warning: major ?? segment.warnings[0]!, distanceM: onSegment ? 0 : ahead };
      break;
    }
    segmentStart = segmentEnd;
  }

  return {
    distanceAlongM: along,
    remainingM,
    remainingS: total > 0 ? Math.round((route.duration_s * remainingM) / total) : 0,
    offRouteM: projection.offsetM,
    isOffRoute: projection.offsetM > OFF_ROUTE_THRESHOLD_M,
    hasArrived: remainingM <= ARRIVAL_THRESHOLD_M && projection.offsetM <= OFF_ROUTE_THRESHOLD_M,
    currentIndex,
    next,
    distanceToNextM,
    upcomingWarning,
  };
}
