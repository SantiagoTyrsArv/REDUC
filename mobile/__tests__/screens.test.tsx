// Screen tests through the accessibility tree: what a screen-reader user perceives.
import { act, fireEvent, screen, waitFor } from "@testing-library/react-native";
import { AccessibilityInfo } from "react-native";

import BarrierScreen from "../app/barrier/[id]";
import MapScreen from "../app/index";
import NavigateScreen from "../app/navigate";
import OnboardingScreen from "../app/onboarding";
import EditProfileScreen from "../app/profiles/[id]";
import ProfilesScreen from "../app/profiles/index";
import RouteScreen from "../app/route/index";
import SegmentsScreen from "../app/route/segments";
import SearchScreen from "../app/search";
import SettingsScreen from "../app/settings";
import { usePlacesStore } from "../src/stores/places";
import { usePlanStore } from "../src/stores/plan";
import { useProfileStore } from "../src/stores/profiles";
import { useSettingsStore } from "../src/stores/settings";
import {
  blockingBarrier,
  mockApi,
  noRouteResponse,
  presets,
  region,
  renderScreen,
  resetStores,
  route,
  router,
  routesResponse,
  setRouteParams,
} from "./helpers";

const announceSpy = jest.spyOn(AccessibilityInfo, "announceForAccessibility").mockImplementation(() => undefined);
const destination = { id: "poi-1", name: "Biblioteca", location: [0.0009, 0.0009] as [number, number] };

beforeEach(() => {
  resetStores();
  announceSpy.mockClear();
});

describe("onboarding", () => {
  it("creates the profile from a template and opens the map", async () => {
    useSettingsStore.setState({ onboardingDone: false });
    useProfileStore.setState({ profiles: [], activeProfileId: null });
    mockApi({ "/v1/profiles/presets": { body: presets } });
    await renderScreen(<OnboardingScreen />);

    const start = screen.getByTestId("onboarding-start");
    expect(start).toBeDisabled();
    await fireEvent.press(await screen.findByTestId("preset-electric"));
    expect(screen.getByTestId("preset-electric")).toBeSelected();
    await fireEvent.press(start);

    const { profiles, activeProfileId } = useProfileStore.getState();
    expect(profiles).toHaveLength(1);
    expect(profiles[0]?.name).toBe("Silla eléctrica");
    expect(profiles[0]?.profile.device).toBe("electric");
    expect(activeProfileId).toBe(profiles[0]?.id);
    expect(useSettingsStore.getState().onboardingDone).toBe(true);
    expect(router.replace).toHaveBeenCalledWith("/");
  });

  it("asks for the location permission only when the user presses the button", async () => {
    useSettingsStore.setState({ onboardingDone: false });
    mockApi({ "/v1/profiles/presets": { body: presets } });
    await renderScreen(<OnboardingScreen />);
    await fireEvent.press(screen.getByTestId("onboarding-location"));
    expect(await screen.findByText(/Ubicación permitida/)).toBeOnTheScreen();
  });
});

describe("main map", () => {
  it("redirects to onboarding on first use", async () => {
    useSettingsStore.setState({ onboardingDone: false });
    mockApi({ "/v1/regions": { body: [region] } });
    await renderScreen(<MapScreen />);
    expect(screen.getByTestId("redirect")).toHaveTextContent("/onboarding");
  });

  it("offers the search, the layer toggle and the legend with labels", async () => {
    mockApi({ "/v1/regions": { body: [region] } });
    await renderScreen(<MapScreen />);

    expect(screen.getByLabelText("Mapa de accesibilidad de Zona de prueba")).toBeOnTheScreen();
    expect(screen.getByLabelText("Perfil: Mi silla")).toBeOnTheScreen();
    await fireEvent.press(screen.getByLabelText("¿A dónde vas?"));
    expect(router.push).toHaveBeenCalledWith("/search?target=destination");

    await fireEvent.press(screen.getByLabelText("Ocultar capa de accesibilidad"));
    expect(useSettingsStore.getState().showAccessibilityLayer).toBe(false);
    expect(screen.getByLabelText("Mostrar capa de accesibilidad")).toBeOnTheScreen();

    await fireEvent.press(screen.getByTestId("map-legend"));
    expect(await screen.findByText("Precaución: línea discontinua ámbar")).toBeOnTheScreen();

    await fireEvent.press(screen.getByTestId("map-center"));
    expect(screen.getByTestId("map-message")).toHaveTextContent("Todavía no conocemos tu ubicación");
  });

  it("explains when no region is published", async () => {
    mockApi({ "/v1/regions": { body: [] } });
    await renderScreen(<MapScreen />);
    expect(await screen.findByText("No hay ninguna zona disponible todavía.")).toBeOnTheScreen();
  });
});

describe("search", () => {
  const poi = {
    id: "poi-1",
    name: "Biblioteca",
    category: "building",
    location: [0.0009, 0.0009],
    accessible_entrance: true,
  };

  it("lists places, stores the destination and remembers it as recent", async () => {
    const api = mockApi({ "/pois": { body: [poi] } });
    await renderScreen(<SearchScreen />);

    const row = await screen.findByTestId("poi-poi-1");
    expect(row).toHaveProp("accessibilityLabel", "Biblioteca. Edificio · Entrada accesible");
    expect(api.calls[0]?.url).toContain("/v1/regions/zona-prueba/pois");

    await fireEvent.press(screen.getByLabelText("Añadir Biblioteca a favoritos"));
    expect(usePlacesStore.getState().favorites).toHaveLength(1);

    await fireEvent.press(row);
    expect(usePlanStore.getState().destination?.name).toBe("Biblioteca");
    expect(usePlacesStore.getState().recents[0]?.id).toBe("poi-1");
    expect(router.replace).toHaveBeenCalledWith("/route");
  });

  it("lets the user choose a point on the map or the current location as origin", async () => {
    setRouteParams({ target: "origin" });
    usePlanStore.setState({ origin: destination });
    mockApi({ "/pois": { body: [] } });
    await renderScreen(<SearchScreen />);

    expect(await screen.findByText("No hay lugares que coincidan")).toBeOnTheScreen();
    await fireEvent.press(screen.getByTestId("search-current"));
    expect(usePlanStore.getState().origin).toBeNull();

    await fireEvent.press(screen.getByTestId("search-pick-map"));
    expect(usePlanStore.getState().pickTarget).toBe("origin");
    expect(router.dismissTo).toHaveBeenCalledWith("/");
  });
});

describe("route planning", () => {
  beforeEach(() => {
    usePlanStore.setState({ position: [0, 0], destination });
  });

  it("shows the routes, explains the shortest one and announces the result", async () => {
    const api = mockApi({ "/v1/routes": { body: routesResponse } });
    await renderScreen(<RouteScreen />);

    const recommended = await screen.findByTestId("route-card-0");
    expect(recommended).toHaveProp(
      "accessibilityLabel",
      "Ruta recomendada: 200 m, 4 minutos, accesibilidad 82 de 100, pendiente máxima: 4,5 % de subida. Precaución. 1 tramo con precaución",
    );
    expect(recommended).toBeSelected();
    expect(api.calls[0]?.body).toMatchObject({
      origin: [0, 0],
      destination: [0.0009, 0.0009],
      alternatives: 2,
      include_shortest: true,
      locale: "es",
      profile: { device: "manual", max_step_cm: 2 },
    });

    // The reason to avoid the shortest route is given in words, with the barrier reachable.
    expect(screen.getByText("La ruta más corta mide 150 m: 50 m menos que la recomendada.")).toBeOnTheScreen();
    expect(screen.getByText("Pero pasa por 1 barrera que no puedes cruzar:")).toBeOnTheScreen();
    await fireEvent.press(screen.getByTestId(`blocking-${blockingBarrier.id}`));
    expect(router.push).toHaveBeenCalledWith(`/barrier/${blockingBarrier.id}`);

    expect(screen.getByLabelText("Aviso: Pendiente de subida del 4,5 % durante 100 m")).toBeOnTheScreen();
    expect(announceSpy).toHaveBeenCalledWith(expect.stringContaining("2 rutas calculadas"));

    await fireEvent.press(screen.getByTestId("route-card-1"));
    expect(usePlanStore.getState().selectedRouteId).toBe("r2");

    await fireEvent.press(screen.getByTestId("route-start"));
    expect(usePlanStore.getState().activeRoute?.id).toBe("r2");
    expect(router.push).toHaveBeenCalledWith("/navigate");
  });

  it("says clearly when there is no accessible route and never offers to start", async () => {
    mockApi({ "/v1/routes": { status: 422, body: noRouteResponse(null) } });
    await renderScreen(<RouteScreen />);

    expect(await screen.findByText("No existe una ruta accesible")).toBeOnTheScreen();
    expect(
      screen.getByText("Ninguna ruta evita las barreras críticas para tu perfil. No te proponemos un camino inseguro."),
    ).toBeOnTheScreen();
    expect(screen.getByText("Escalera de 8 escalones")).toBeOnTheScreen();
    expect(screen.queryByTestId("route-start")).toBeNull();
    expect(announceSpy).toHaveBeenCalledWith(expect.stringContaining("No existe una ruta accesible"));
  });

  it("marks the fallback route as exceeding the profile", async () => {
    mockApi({ "/v1/routes": { status: 422, body: noRouteResponse(route) } });
    await renderScreen(<RouteScreen />);

    expect(await screen.findByText("Alternativa que supera tu perfil")).toBeOnTheScreen();
    expect(screen.getByText("• Pendiente hasta 2 puntos por encima de tu límite")).toBeOnTheScreen();
    expect(screen.getByTestId("route-start")).toHaveProp("accessibilityLabel", "Iniciar de todos modos");
  });

  it("shows the server explanation for a point outside the region and allows retrying", async () => {
    mockApi({
      "/v1/routes": {
        status: 422,
        body: { type: "outside_region", title: "Fuera de la zona cubierta", status: 422, detail: "Fuera de la región" },
      },
    });
    await renderScreen(<RouteScreen />);
    expect(await screen.findByText("Fuera de la región")).toBeOnTheScreen();
    expect(screen.getByTestId("route-retry")).toBeOnTheScreen();
  });

  it("asks for the missing pieces instead of calling the API", async () => {
    usePlanStore.setState({ position: null, destination });
    const api = mockApi({});
    await renderScreen(<RouteScreen />);
    expect(screen.getByText("Falta el origen")).toBeOnTheScreen();
    expect(api.calls).toHaveLength(0);
  });
});

describe("route segments", () => {
  it("describes every segment in one sentence, without the map", async () => {
    usePlanStore.setState({ position: [0, 0], destination });
    mockApi({ "/v1/routes": { body: routesResponse } });
    await renderScreen(<SegmentsScreen />);

    expect(await screen.findByTestId("segments-intro")).toHaveTextContent(
      "2 tramos, 200 m en total. Lista en orden de recorrido.",
    );
    expect(screen.getByTestId("segment-0")).toHaveProp(
      "accessibilityLabel",
      "Tramo 1 de 2. Accesible. 100 m. Pendiente: 0,5 % de subida. Superficie lisa. Sin avisos",
    );
    expect(screen.getByTestId("segment-1")).toHaveProp(
      "accessibilityLabel",
      "Tramo 2 de 2. Precaución. 100 m. Pendiente: 4,5 % de subida. Superficie buena. Pendiente de subida del 4,5 % durante 100 m",
    );
    expect(screen.getByTestId("instruction-1")).toHaveTextContent("2. Gira a la izquierda y continúa 100 m");
  });

  it("invites to plan a route when there is none", async () => {
    mockApi({});
    await renderScreen(<SegmentsScreen />);
    expect(screen.getByText("Calcula una ruta para ver sus tramos.")).toBeOnTheScreen();
  });
});

describe("navigation", () => {
  it("shows the current instruction, the next one and the remaining distance", async () => {
    usePlanStore.setState({ activeRoute: route, position: [0.0001, 0] });
    mockApi({});
    await renderScreen(<NavigateScreen />);

    expect(screen.getByTestId("navigate-current")).toHaveTextContent(/Sal hacia el este y continúa 100 m/);
    expect(screen.getByTestId("navigate-next")).toHaveTextContent(/Después, en 89 m/);
    expect(screen.getByTestId("navigate-remaining")).toHaveProp("accessibilityLabel", "Quedan 189 m, unos 4 minutos");
  });

  it("announces the next warning once when it gets close", async () => {
    usePlanStore.setState({ activeRoute: route, position: [0.0001, 0] });
    mockApi({});
    await renderScreen(<NavigateScreen />);
    expect(announceSpy).not.toHaveBeenCalled();

    await act(async () => usePlanStore.getState().setPosition([0.0007, 0]));
    await act(async () => usePlanStore.getState().setPosition([0.00075, 0]));
    const warnings = announceSpy.mock.calls.filter(([text]) => String(text).includes("Pendiente de subida"));
    expect(warnings).toHaveLength(1);
    expect(screen.getByText("Pendiente de subida del 4,5 % durante 100 m")).toBeOnTheScreen();
  });

  it("recalculates from the current position after a deviation above 25 m", async () => {
    usePlanStore.setState({ activeRoute: route, position: [0.0001, 0] });
    const recalculated = { ...route, id: "r-new" };
    const api = mockApi({ "/v1/routes": { body: { ...routesResponse, routes: [recalculated] } } });
    await renderScreen(<NavigateScreen />);
    expect(api.calls).toHaveLength(0);

    await act(async () => usePlanStore.getState().setPosition([0.0004, 0.0004]));
    await waitFor(() => expect(usePlanStore.getState().activeRoute?.id).toBe("r-new"));
    expect(api.calls).toHaveLength(1);
    expect(api.calls[0]?.body).toMatchObject({ origin: [0.0004, 0.0004], destination: [0.0009, 0.0009] });
    expect(announceSpy).toHaveBeenCalledWith("Recalculando la ruta…");
    expect(announceSpy).toHaveBeenCalledWith("Ruta recalculada");
  });

  it("keeps the current route when the recalculation finds nothing accessible", async () => {
    usePlanStore.setState({ activeRoute: route, position: [0.0004, 0.0004] });
    mockApi({ "/v1/routes": { status: 422, body: noRouteResponse(route) } });
    await renderScreen(<NavigateScreen />);

    expect(await screen.findByText("Desde aquí no hay una ruta accesible. Vuelve a la ruta marcada.")).toBeOnTheScreen();
    expect(usePlanStore.getState().activeRoute?.id).toBe("r1");
  });

  it("announces the arrival and lets the user finish", async () => {
    usePlanStore.setState({ activeRoute: route, position: [0.0009, 0.00088] });
    mockApi({});
    await renderScreen(<NavigateScreen />);

    expect(screen.getByText("Has llegado a tu destino")).toBeOnTheScreen();
    expect(announceSpy).toHaveBeenCalledWith("Has llegado a tu destino");
    await fireEvent.press(screen.getByTestId("navigate-finish"));
    expect(usePlanStore.getState().activeRoute).toBeNull();
    expect(router.dismissTo).toHaveBeenCalledWith("/");
  });
});

describe("barrier details", () => {
  const barrier = {
    id: blockingBarrier.id,
    class: "stairs",
    severity: "critical",
    location: [0.0004, 0.0004],
    confidence: 0.91,
    verification_status: "confirmed",
    n_observations: 4,
    description: "Escalera de 8 escalones",
    photo_url: "https://example.test/crop.jpg",
    attribution: "© Mapillary, CC BY-SA",
    source: "cv",
    attributes: { step_count: 8 },
  };

  it("describes the barrier with its confidence, verification and attribution", async () => {
    setRouteParams({ id: barrier.id });
    mockApi({ "/v1/barriers/": { body: barrier } });
    await renderScreen(<BarrierScreen />);

    expect(await screen.findByTestId("barrier-title")).toHaveTextContent("Escalera de 8 escalones");
    expect(screen.getByLabelText("Gravedad: Crítica: no se puede cruzar")).toBeOnTheScreen();
    expect(screen.getByLabelText("Confianza de la detección: 91 %")).toBeOnTheScreen();
    expect(screen.getByLabelText("Verificación: Confirmada por una persona")).toBeOnTheScreen();
    expect(screen.getByLabelText("Observaciones: 4 observaciones")).toBeOnTheScreen();
    expect(screen.getByLabelText("Foto de la barrera: Escalera de 8 escalones")).toBeOnTheScreen();
    expect(screen.getByText("© Mapillary, CC BY-SA")).toBeOnTheScreen();
    expect(screen.getByText("Datos del mapa © colaboradores de OpenStreetMap")).toBeOnTheScreen();
  });

  it("explains a missing barrier", async () => {
    setRouteParams({ id: "missing" });
    mockApi({
      "/v1/barriers/": { status: 404, body: { type: "not_found", title: "No encontrado", status: 404, detail: "x" } },
    });
    await renderScreen(<BarrierScreen />);
    expect(await screen.findByText("No encontramos lo que buscabas.")).toBeOnTheScreen();
  });
});

describe("profiles", () => {
  it("creates a profile from a template, activates and deletes", async () => {
    mockApi({ "/v1/profiles/presets": { body: presets } });
    await renderScreen(<ProfilesScreen />);

    await fireEvent.press(await screen.findByTestId("profile-create-electric"));
    const created = useProfileStore.getState().profiles[1]!;
    expect(created.profile.device).toBe("electric");
    expect(router.push).toHaveBeenCalledWith(`/profiles/${created.id}`);

    await fireEvent.press(screen.getByTestId(`profile-activate-${created.id}`));
    expect(useProfileStore.getState().activeProfileId).toBe(created.id);

    await fireEvent.press(screen.getByLabelText("Eliminar Mi silla"));
    expect(useProfileStore.getState().profiles.map((item) => item.id)).toEqual([created.id]);
  });

  it("edits limits with buttons and shows every value as text", async () => {
    setRouteParams({ id: "p1" });
    mockApi({});
    await renderScreen(<EditProfileScreen />);

    expect(screen.getByTestId("value-max_uphill_pct")).toHaveTextContent("6 %");
    await fireEvent.press(screen.getByLabelText("Aumentar Subida máxima"));
    expect(screen.getByTestId("value-max_uphill_pct")).toHaveTextContent("6,5 %");
    expect(useProfileStore.getState().profiles[0]?.profile.max_uphill_pct).toBe(6.5);

    expect(screen.getByTestId("value-max_surface_class")).toHaveTextContent("2 · irregular");
    await fireEvent.press(screen.getByLabelText("Reducir Escalón máximo"));
    expect(useProfileStore.getState().profiles[0]?.profile.max_step_cm).toBe(1.5);

    await fireEvent(screen.getByTestId("switch-avoid_unverified"), "valueChange", true);
    expect(useProfileStore.getState().profiles[0]?.profile.avoid_unverified).toBe(true);

    await fireEvent.changeText(screen.getByTestId("profile-name"), "Silla nueva");
    expect(useProfileStore.getState().profiles[0]?.name).toBe("Silla nueva");
  });
});

describe("settings", () => {
  it("changes language, units, region and demo location", async () => {
    mockApi({ "/v1/regions": { body: [region] } });
    await renderScreen(<SettingsScreen />);

    await fireEvent.press(screen.getByTestId("settings-units-imperial"));
    expect(useSettingsStore.getState().units).toBe("imperial");

    await fireEvent.press(await screen.findByTestId("settings-region-zona-prueba"));
    expect(useSettingsStore.getState().regionSlug).toBe("zona-prueba");

    await fireEvent(screen.getByTestId("settings-demoLocation"), "valueChange", true);
    expect(useSettingsStore.getState().demoLocation).toBe(true);

    await fireEvent.press(screen.getByTestId("settings-language-en"));
    expect(await screen.findByText("Language")).toBeOnTheScreen();
    expect(screen.getByText("Map data © OpenStreetMap contributors (ODbL).")).toBeOnTheScreen();
  });
});
