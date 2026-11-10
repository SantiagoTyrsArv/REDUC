"""Localized texts for route warnings, instructions and barrier descriptions."""

from typing import Any, Literal

Locale = Literal["es", "en"]
SUPPORTED_LOCALES: tuple[Locale, ...] = ("es", "en")
DEFAULT_LOCALE: Locale = "es"

_CATALOG: dict[Locale, dict[str, str]] = {
    "es": {
        "warning.slope_moderate": "Pendiente de subida del {slope} % durante {length} m",
        "warning.slope_steep_downhill": "Bajada pronunciada del {slope} % durante {length} m",
        "warning.surface_irregular": "Superficie irregular durante {length} m",
        "warning.unverified_segment": "Tramo sin verificar durante {length} m",
        "warning.curb_ramp_unknown": "Cruce sin información sobre la rampa del bordillo",
        "warning.narrow_passage": "Paso estrecho de {width} m de ancho",
        "warning.road_shoulder": "Sin acera: {length} m por el borde de la vía",
        "warning.exceeds_profile": "Este tramo supera los límites de tu perfil ({length} m)",
        "instruction.depart": "Sal hacia el {direction} y continúa {distance} m",
        "instruction.left": "Gira a la izquierda y continúa {distance} m",
        "instruction.right": "Gira a la derecha y continúa {distance} m",
        "instruction.left_poi": "Gira a la izquierda junto a {poi} y continúa {distance} m",
        "instruction.right_poi": "Gira a la derecha junto a {poi} y continúa {distance} m",
        "instruction.u_turn": "Da la vuelta y continúa {distance} m",
        "instruction.arrive": "Has llegado a tu destino",
        "direction.n": "norte",
        "direction.ne": "noreste",
        "direction.e": "este",
        "direction.se": "sureste",
        "direction.s": "sur",
        "direction.sw": "suroeste",
        "direction.w": "oeste",
        "direction.nw": "noroeste",
        "barrier.stairs": "Escalera",
        "barrier.stairs_count": "Escalera de {step_count} escalones",
        "barrier.single_step": "Escalón",
        "barrier.single_step_height": "Escalón de {step_height_cm} cm",
        "barrier.curb_no_ramp": "Bordillo sin rampa",
        "barrier.obstacle": "Obstáculo en la acera",
        "barrier.surface_damage": "Superficie dañada",
        "barrier.steep_slope_visual": "Pendiente pronunciada",
        "barrier.no_sidewalk": "Sin acera",
        "barrier.narrow_sidewalk": "Acera estrecha",
        "barrier.other": "Barrera",
        "error.outside_region.title": "Fuera de la zona cubierta",
        "error.outside_region.detail": "El origen y el destino deben estar dentro de una misma región activa",
        "error.no_nearby_path.title": "Sin camino cercano",
        "error.no_nearby_path.origin": "No hay un tramo peatonal a menos de 50 m del origen",
        "error.no_nearby_path.destination": "No hay un tramo peatonal a menos de 50 m del destino",
        "error.no_accessible_route.title": "No existe una ruta accesible",
        "error.no_accessible_route.fallback": "Ninguna ruta cumple tu perfil. Te mostramos la alternativa menos mala.",
        "error.no_accessible_route.none": "Ninguna ruta evita las barreras críticas para tu perfil",
    },
    "en": {
        "warning.slope_moderate": "Uphill slope of {slope}% for {length} m",
        "warning.slope_steep_downhill": "Steep downhill of {slope}% for {length} m",
        "warning.surface_irregular": "Uneven surface for {length} m",
        "warning.unverified_segment": "Unverified segment for {length} m",
        "warning.curb_ramp_unknown": "Crossing with no curb ramp information",
        "warning.narrow_passage": "Narrow passage, {width} m wide",
        "warning.road_shoulder": "No sidewalk: {length} m along the road edge",
        "warning.exceeds_profile": "This segment exceeds your profile limits ({length} m)",
        "instruction.depart": "Head {direction} and continue for {distance} m",
        "instruction.left": "Turn left and continue for {distance} m",
        "instruction.right": "Turn right and continue for {distance} m",
        "instruction.left_poi": "Turn left next to {poi} and continue for {distance} m",
        "instruction.right_poi": "Turn right next to {poi} and continue for {distance} m",
        "instruction.u_turn": "Turn around and continue for {distance} m",
        "instruction.arrive": "You have arrived at your destination",
        "direction.n": "north",
        "direction.ne": "northeast",
        "direction.e": "east",
        "direction.se": "southeast",
        "direction.s": "south",
        "direction.sw": "southwest",
        "direction.w": "west",
        "direction.nw": "northwest",
        "barrier.stairs": "Stairs",
        "barrier.stairs_count": "Staircase with {step_count} steps",
        "barrier.single_step": "Step",
        "barrier.single_step_height": "{step_height_cm} cm step",
        "barrier.curb_no_ramp": "Curb without ramp",
        "barrier.obstacle": "Obstacle on the sidewalk",
        "barrier.surface_damage": "Damaged surface",
        "barrier.steep_slope_visual": "Steep slope",
        "barrier.no_sidewalk": "No sidewalk",
        "barrier.narrow_sidewalk": "Narrow sidewalk",
        "barrier.other": "Barrier",
        "error.outside_region.title": "Outside the covered area",
        "error.outside_region.detail": "Origin and destination must be inside the same active region",
        "error.no_nearby_path.title": "No nearby path",
        "error.no_nearby_path.origin": "There is no pedestrian path within 50 m of the origin",
        "error.no_nearby_path.destination": "There is no pedestrian path within 50 m of the destination",
        "error.no_accessible_route.title": "No accessible route exists",
        "error.no_accessible_route.fallback": "No route meets your profile. Showing the least-bad alternative.",
        "error.no_accessible_route.none": "No route avoids the critical barriers for your profile",
    },
}


def normalize_locale(locale: str | None) -> Locale:
    """Map any requested locale to a supported one, defaulting to Spanish."""
    if locale is not None and locale.lower().startswith("en"):
        return "en"
    return DEFAULT_LOCALE


def translate(locale: Locale, key: str, **params: Any) -> str:
    """Render one catalog entry; unknown keys fail loudly so tests catch missing texts."""
    return _CATALOG[locale][key].format(**params)


def barrier_message(locale: Locale, barrier_class: str, attributes: dict[str, Any]) -> str:
    """Describe a barrier using its measured attributes when they are available."""
    step_count = attributes.get("step_count")
    if barrier_class == "stairs" and isinstance(step_count, int) and step_count > 0:
        return translate(locale, "barrier.stairs_count", step_count=step_count)
    step_height = attributes.get("step_height_cm")
    if barrier_class == "single_step" and isinstance(step_height, int | float):
        return translate(locale, "barrier.single_step_height", step_height_cm=round(float(step_height)))
    key = f"barrier.{barrier_class}"
    return translate(locale, key if key in _CATALOG[locale] else "barrier.other")
