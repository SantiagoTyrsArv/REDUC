// Live navigation state (RF-10): progress along the active route, automatic recalculation
// when the user strays more than 25 m, and spoken announcements of the important changes.
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { announce } from "../../lib/a11y";
import { fetchRoutes } from "../../lib/api";
import { formatDistance } from "../../lib/format";
import { pointAlongLine, type LonLat } from "../../lib/geo";
import { usePlanStore } from "../../stores/plan";
import { selectActiveProfile, useProfileStore } from "../../stores/profiles";
import { useSettingsStore } from "../../stores/settings";
import { computeProgress, type NavigationProgress } from "./progress";

/** Minimum pause between two recalculations, so a noisy GPS cannot flood the API. */
export const RECALC_COOLDOWN_MS = 8000;
const SIMULATION_TICK_MS = 1000;

export type RecalcState = "idle" | "running" | "failed" | "no_route";

export interface NavigationSession {
  progress: NavigationProgress | null;
  recalc: RecalcState;
  simulating: boolean;
  toggleSimulation: () => void;
}

export function useNavigationSession(): NavigationSession {
  const { t, i18n } = useTranslation();
  const route = usePlanStore((state) => state.activeRoute);
  const position = usePlanStore((state) => state.position);
  const units = useSettingsStore((state) => state.units);
  const [recalc, setRecalc] = useState<RecalcState>("idle");
  const [simulating, setSimulating] = useState(false);
  const lastRecalcAt = useRef(0);
  const announcedWarning = useRef<string | null>(null);
  const announcedArrival = useRef(false);
  const simulatedM = useRef(0);

  const progress = route && position ? computeProgress(route, position) : null;
  const routeId = route?.id ?? null;

  useEffect(() => {
    announcedWarning.current = null;
    announcedArrival.current = false;
    simulatedM.current = 0;
  }, [routeId]);

  // Recalculate from the current position when the user leaves the route.
  const isOffRoute = progress?.isOffRoute ?? false;
  useEffect(() => {
    if (!isOffRoute || !route || !position || recalc === "running") {
      return;
    }
    const now = Date.now();
    if (now - lastRecalcAt.current < RECALC_COOLDOWN_MS) {
      return;
    }
    const profile = selectActiveProfile(useProfileStore.getState());
    const destination = route.geometry.coordinates[route.geometry.coordinates.length - 1] as LonLat | undefined;
    if (!profile || !destination) {
      return;
    }
    lastRecalcAt.current = now;
    setRecalc("running");
    announce(t("navigate.recalculating"));
    let cancelled = false;
    fetchRoutes({ origin: position, destination, profile: profile.profile, locale: i18n.language === "en" ? "en" : "es" })
      .then((result) => {
        if (cancelled) {
          return;
        }
        const next = result.kind === "ok" ? result.data.routes[0] : undefined;
        if (next) {
          usePlanStore.getState().startNavigation(next);
          setRecalc("idle");
          announce(t("navigate.recalculated"));
        } else {
          // Never switch silently to a route that exceeds the profile.
          setRecalc("no_route");
          announce(t("navigate.recalcNoRoute"));
        }
      })
      .catch(() => {
        if (!cancelled) {
          setRecalc("failed");
          announce(t("navigate.recalcFailed"));
        }
      });
    return () => {
      cancelled = true;
    };
    // Position changes re-run this effect; the cooldown above limits the requests.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOffRoute, position?.[0], position?.[1], routeId]);

  // Back on the route: clear a previous failure message.
  useEffect(() => {
    if (!isOffRoute && (recalc === "failed" || recalc === "no_route")) {
      setRecalc("idle");
    }
  }, [isOffRoute, recalc]);

  const warningKey = progress?.upcomingWarning ? progress.upcomingWarning.warning.message : null;
  const warningDistance = progress?.upcomingWarning?.distanceM ?? 0;
  useEffect(() => {
    if (warningKey && announcedWarning.current !== warningKey) {
      announcedWarning.current = warningKey;
      const lead =
        warningDistance > 0
          ? t("navigate.warningAhead", { distance: formatDistance(warningDistance, units) })
          : t("navigate.warningNow");
      announce(`${lead}. ${warningKey}`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [warningKey]);

  const hasArrived = progress?.hasArrived ?? false;
  useEffect(() => {
    if (hasArrived && !announcedArrival.current) {
      announcedArrival.current = true;
      setSimulating(false);
      announce(t("navigate.arrivedTitle"));
    }
  }, [hasArrived, t]);

  // Demo mode: walk along the route at the profile speed so the flow can be tried anywhere.
  useEffect(() => {
    if (!simulating || !route) {
      return undefined;
    }
    const speed = selectActiveProfile(useProfileStore.getState())?.profile.speed_mps ?? 1;
    const coords = route.geometry.coordinates as LonLat[];
    const timer = setInterval(() => {
      // Sped up 8x: a demo should not take as long as the real trip.
      simulatedM.current = Math.min(route.distance_m, simulatedM.current + speed * 8);
      const next = pointAlongLine(coords, simulatedM.current);
      if (next) {
        usePlanStore.getState().setPosition(next);
      }
    }, SIMULATION_TICK_MS);
    return () => clearInterval(timer);
  }, [simulating, route]);

  return {
    progress,
    recalc,
    simulating,
    toggleSimulation: () => setSimulating((value) => !value),
  };
}
