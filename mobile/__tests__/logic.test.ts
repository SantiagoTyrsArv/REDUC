import { NUMERIC_FIELDS, getNumeric, normalize, setNumeric } from "../src/features/profiles/fields";
import { pickRegion } from "../src/features/region/useActiveRegion";
import { altRoutesData, markersData, selectedRouteData, tileUrl } from "../src/features/map/data";
import { edgeLayers } from "../src/features/map/layers";
import { computeProgress, OFF_ROUTE_THRESHOLD_M } from "../src/features/navigation/progress";
import { routeStatus, toMapRoutes, uniqueWarnings } from "../src/features/routes/plan";
import { routeQueryKey } from "../src/lib/api";
import { durationMinutes, formatDistance } from "../src/lib/format";
import {
  boundsOf,
  geometryContains,
  haversineM,
  lineLengthM,
  pointAlongLine,
  projectOnLine,
  roundToGrid,
  type LonLat,
} from "../src/lib/geo";
import { lightPalette } from "../src/theme";
import { manualProfile, region, route } from "./helpers";

describe("geo", () => {
  it("measures distances at walking scale", () => {
    expect(haversineM([0, 0], [0.0009, 0])).toBeCloseTo(100.1, 0);
    expect(lineLengthM(route.geometry.coordinates as LonLat[])).toBeCloseTo(200.2, 0);
  });

  it("projects a position onto a line with its offset", () => {
    const projection = projectOnLine(route.geometry.coordinates as LonLat[], [0.00045, 0.0001]);
    expect(projection?.distanceAlongM).toBeCloseTo(50, 0);
    expect(projection?.offsetM).toBeCloseTo(11.1, 0);
    expect(projectOnLine([], [0, 0])).toBeNull();
  });

  it("finds points along a line and clamps to its ends", () => {
    const coords = route.geometry.coordinates as LonLat[];
    expect(pointAlongLine(coords, 0)).toEqual([0, 0]);
    expect(pointAlongLine(coords, 1e6)).toEqual([0.0009, 0.0009]);
    const middle = pointAlongLine(coords, 150)!;
    expect(middle[0]).toBeCloseTo(0.0009, 6);
    expect(middle[1]).toBeCloseTo(0.00045, 5);
  });

  it("tests containment in polygons with holes", () => {
    expect(geometryContains(region.boundary, [0.001, 0.001])).toBe(true);
    expect(geometryContains(region.boundary, [0.01, 0.001])).toBe(false);
    const withHole = {
      type: "Polygon",
      coordinates: [
        [
          [0, 0],
          [10, 0],
          [10, 10],
          [0, 10],
          [0, 0],
        ],
        [
          [4, 4],
          [6, 4],
          [6, 6],
          [4, 6],
          [4, 4],
        ],
      ],
    };
    expect(geometryContains(withHole, [5, 5])).toBe(false);
    expect(geometryContains(withHole, [2, 2])).toBe(true);
    expect(geometryContains({ type: "Point" }, [0, 0])).toBe(false);
  });

  it("builds bounds and pads a single point", () => {
    expect(boundsOf([])).toBeNull();
    expect(boundsOf(route.geometry.coordinates as LonLat[])).toEqual([0, 0, 0.0009, 0.0009]);
    const single = boundsOf([[1, 2]])!;
    expect(single[2] - single[0]).toBeGreaterThan(0);
  });

  it("rounds nearby origins to the same cache key", () => {
    const a = routeQueryKey({ origin: [0.000011, 0], destination: [1, 1], profile: manualProfile, locale: "es" });
    const b = routeQueryKey({ origin: [0.000019, 0], destination: [1, 1], profile: manualProfile, locale: "es" });
    const far = routeQueryKey({ origin: [0.0003, 0], destination: [1, 1], profile: manualProfile, locale: "es" });
    expect(a).toEqual(b);
    expect(a).not.toEqual(far);
    expect(roundToGrid([0.00012, 0.00013])[0]).toBeCloseTo(0.0001, 6);
    expect(routeQueryKey(null)).toEqual(["routes", "idle"]);
  });
});

describe("format", () => {
  it("formats metric and imperial distances", () => {
    expect(formatDistance(84.4, "metric")).toBe("84 m");
    expect(formatDistance(1530, "metric")).toBe("1.5 km");
    expect(formatDistance(100, "imperial")).toBe("330 ft");
    expect(formatDistance(3000, "imperial")).toBe("1.9 mi");
  });

  it("never under-promises durations", () => {
    expect(durationMinutes(0)).toBe(1);
    expect(durationMinutes(61)).toBe(2);
  });
});

describe("navigation progress", () => {
  it("follows the first instruction at the start", () => {
    const progress = computeProgress(route, [0.0001, 0])!;
    expect(progress.currentIndex).toBe(0);
    expect(progress.next?.maneuver).toBe("left");
    expect(progress.distanceToNextM).toBeCloseTo(89, 0);
    expect(progress.isOffRoute).toBe(false);
    expect(progress.hasArrived).toBe(false);
    expect(progress.remainingS).toBeGreaterThan(0);
  });

  it("announces a warning shortly before its segment and while on it", () => {
    expect(computeProgress(route, [0.0001, 0])!.upcomingWarning).toBeNull();
    const near = computeProgress(route, [0.0007, 0])!;
    expect(near.upcomingWarning?.warning.code).toBe("slope_moderate");
    expect(near.upcomingWarning?.distanceM).toBeGreaterThan(0);
    const on = computeProgress(route, [0.0009, 0.0004])!;
    expect(on.upcomingWarning?.distanceM).toBe(0);
    expect(on.currentIndex).toBe(1);
  });

  it("detects deviations above the recalculation threshold", () => {
    const off = computeProgress(route, [0.0004, 0.0004])!;
    expect(off.offRouteM).toBeGreaterThan(OFF_ROUTE_THRESHOLD_M);
    expect(off.isOffRoute).toBe(true);
    expect(computeProgress(route, [0.0004, 0.0001])!.isOffRoute).toBe(false);
  });

  it("detects the arrival", () => {
    const arrived = computeProgress(route, [0.0009, 0.00088])!;
    expect(arrived.hasArrived).toBe(true);
    expect(arrived.next?.maneuver).toBe("arrive");
  });
});

describe("route helpers", () => {
  it("summarises the worst status of a route", () => {
    expect(routeStatus(route)).toBe("caution");
    expect(routeStatus({ ...route, caution_segments: 0, segments: [route.segments[0]!] })).toBe("accessible");
    expect(
      routeStatus({ ...route, segments: [{ ...route.segments[0]!, status: "inaccessible" }] }),
    ).toBe("inaccessible");
  });

  it("deduplicates warnings and puts the major ones first", () => {
    const major = { code: "exceeds_profile", severity: "major" as const, message: "Supera tu perfil" };
    const doubled = {
      ...route,
      segments: [route.segments[1]!, { ...route.segments[1]!, warnings: [...route.segments[1]!.warnings, major] }],
    };
    expect(uniqueWarnings(doubled).map((warning) => warning.code)).toEqual(["exceeds_profile", "slope_moderate"]);
  });

  it("only gives per-segment styling to the selected route", () => {
    const mapped = toMapRoutes([route, { ...route, id: "r2" }], "r1");
    expect(mapped[0]?.segments).toHaveLength(2);
    expect(mapped[1]?.segments).toBeUndefined();
    expect(altRoutesData(mapped).features).toHaveLength(1);
    expect(selectedRouteData(mapped).features.map((feature) => feature.properties?.status)).toEqual([
      "accessible",
      "caution",
    ]);
    expect(selectedRouteData([]).features).toHaveLength(0);
  });
});

describe("map layers", () => {
  it("encodes status with a line pattern, not only with colour", () => {
    const layers = edgeLayers(lightPalette);
    const dash = (id: string) => layers.find((layer) => layer.id === id)?.paint["line-dasharray"];
    expect(dash("reduc-edge-accessible")).toBeUndefined();
    expect(dash("reduc-edge-caution")).toBeDefined();
    expect(dash("reduc-edge-inaccessible")).toBeDefined();
    expect(dash("reduc-edge-caution")).not.toEqual(dash("reduc-edge-inaccessible"));
    expect(layers.find((layer) => layer.id === "reduc-edge-unknown")?.paint["line-width"]).toBeLessThan(4);
  });

  it("builds tile URLs and marker features", () => {
    expect(tileUrl("http://tiles", "barrier", 3)).toBe("http://tiles/barrier/{z}/{x}/{y}?v=3");
    expect(tileUrl("http://tiles", "edge_accessibility", null)).toBe("http://tiles/edge_accessibility/{z}/{x}/{y}");
    expect(markersData([{ id: "a", kind: "origin", location: [1, 2] }]).features[0]?.properties).toEqual({
      id: "a",
      kind: "origin",
    });
  });
});

describe("profile fields", () => {
  it("keeps every range inside the API validation limits", () => {
    const limits: Record<string, [number, number]> = {
      max_uphill_pct: [0, 30],
      max_downhill_pct: [0, 30],
      max_cross_slope_pct: [0, 20],
      max_step_cm: [0, 30],
      min_width_m: [0, 3],
      max_surface_class: [0, 4],
      speed_mps: [0, 5],
      weight_slope: [0, 3],
      weight_surface: [0, 3],
      weight_uncertainty: [0, 3],
    };
    for (const field of NUMERIC_FIELDS) {
      const [min, max] = limits[field.key]!;
      expect(field.min).toBeGreaterThanOrEqual(min);
      expect(field.max).toBeLessThanOrEqual(max);
    }
    // Slopes and speed must stay strictly positive for the API.
    for (const key of ["max_uphill_pct", "max_downhill_pct", "max_cross_slope_pct", "speed_mps"]) {
      expect(NUMERIC_FIELDS.find((field) => field.key === key)!.min).toBeGreaterThan(0);
    }
  });

  it("clamps, snaps and writes values without mutating the profile", () => {
    const uphill = NUMERIC_FIELDS.find((field) => field.key === "max_uphill_pct")!;
    const width = NUMERIC_FIELDS.find((field) => field.key === "min_width_m")!;
    const weight = NUMERIC_FIELDS.find((field) => field.key === "weight_slope")!;
    expect(normalize(uphill, 99)).toBe(20);
    expect(normalize(uphill, -5)).toBe(1);
    expect(normalize(width, 0.9 + 0.05)).toBe(0.95);
    const next = setNumeric(manualProfile, uphill, 7.26);
    expect(next.max_uphill_pct).toBe(7.5);
    expect(manualProfile.max_uphill_pct).toBe(6);
    const weighted = setNumeric(manualProfile, weight, 2);
    expect(getNumeric(weighted, "weight_slope")).toBe(2);
    expect(weighted.weights?.surface).toBe(1);
    expect(getNumeric({ ...manualProfile, weights: undefined }, "weight_surface")).toBe(1);
  });
});

describe("region selection", () => {
  const other = { ...region, id: "other", slug: "otra", boundary: { type: "Polygon", coordinates: [] } };

  it("prefers the manual choice, then the containing region, then the first one", () => {
    expect(pickRegion([other, region], "zona-prueba", null)?.slug).toBe("zona-prueba");
    expect(pickRegion([other, region], null, [0.001, 0.001])?.slug).toBe("zona-prueba");
    expect(pickRegion([other, region], null, [5, 5])?.slug).toBe("otra");
    expect(pickRegion([other, region], "missing", null)?.slug).toBe("otra");
    expect(pickRegion([], null, null)).toBeNull();
  });
});
