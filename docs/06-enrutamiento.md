# 06 — Motor de rutas

## 1. Grafo
- Grafo no dirigido en topología pero con **costo dependiente del sentido** (la pendiente cambia de signo). Se usa `pgr_dijkstra`/`pgr_KSP` con `directed := true`, `cost` (source→target) y `reverse_cost` (target→source) calculados en SQL a partir del perfil.
- Un costo negativo o `-1` en pgRouting significa "tramo no transitable" en ese sentido.
- Para cada consulta se limita el grafo al bbox(origen, destino) ampliado 500 m (o 30 % de la distancia, lo mayor). Si no hay ruta, se reintenta con la región completa.

## 2. Perfil de movilidad

```python
@dataclass(frozen=True)
class MobilityProfile:
    device: Literal["manual", "manual_assisted", "electric", "scooter"]
    max_uphill_pct: float
    max_downhill_pct: float
    max_cross_slope_pct: float
    max_step_cm: float
    min_width_m: float
    max_surface_class: int        # 0..4
    require_curb_ramps: bool
    avoid_unverified: bool
    speed_mps: float
    weights: Weights              # slope, surface, uncertainty (0..3, por defecto 1)
```

Plantillas (`GET /v1/profiles/presets`):

| Preset | uphill | downhill | cross | step | ancho | superficie | rampas | velocidad |
|---|---|---|---|---|---|---|---|---|
| `manual` | 6 % | 8 % | 3 % | 2 cm | 0,9 m | 2 | sí | 0,9 m/s |
| `manual_assisted` | 10 % | 10 % | 4 % | 4 cm | 0,9 m | 3 | sí | 1,0 m/s |
| `electric` | 12 % | 10 % | 5 % | 5 cm | 1,0 m | 3 | sí | 1,3 m/s |
| `scooter` | 10 % | 10 % | 5 % | 3 cm | 1,1 m | 2 | sí | 1,5 m/s |

(Valores basados en guías de diseño accesible: ADA/ISO 21542 recomiendan ≤ 8,33 % en rampas y ≤ 2 % de pendiente transversal. Son configurables por el usuario.)

## 3. Función de costo (por sentido)

**Restricciones duras** → tramo prohibido (`-1`):
- `has_steps` y `max_step_height_cm` (o desconocido) > `max_step_cm`
- pendiente en el sentido > `max_uphill_pct` (subida) o < −`max_downhill_pct` (bajada), usando `max_slope_pct`
- pendiente transversal conocida > `max_cross_slope_pct`, comparando su valor absoluto
- `width_m` conocido < `min_width_m`
- `surface_class` > `max_surface_class`
- `obstacle_level = 2`
- `require_curb_ramps` y extremo de cruce con `curb_ramp_* = 'no'`
- `avoid_unverified` y `verified = false`
- Barrera `critical` con `verification_status = 'confirmed'` → **siempre** prohibido. La versión actual de `MobilityProfile` no incluye una tolerancia explícita para estas barreras.

**Costo suave** (metros equivalentes):
```
cost = length_m · (1
      + w.slope       · f_slope(slope_dir)          # 0 en llano, crece cuadrático hasta el límite
      + w.surface     · 0.25 · surface_class
      + 0.3 · (obstacle_level == 1)
      + 0.5 · (kind == 'road_shoulder' or sidewalk_missing)
      + w.uncertainty · 0.6 · (1 − data_confidence)
      + 0.4 · (curb_ramp desconocido en cruce))
```
- `f_slope(s) = (s / límite)²` para subida; para bajada `0.5 · (|s| / límite)²`.
- Cruces con `curb_ramp='unknown'` se permiten pero penalizan; si `require_curb_ramps` y `avoid_unverified`, se prohíben.

La función vive en `core/routing/cost.py` como **una sola fuente de verdad** que genera el fragmento SQL (`build_cost_sql(profile) -> (sql_text, params)`) y también tiene implementación Python equivalente para pruebas. Una prueba de propiedad (Hypothesis) verifica que ambas den el mismo costo.

## 4. Algoritmo
1. Ajustar origen/destino al punto más cercano sobre un tramo (≤ 50 m) y partir ese tramo virtualmente (`pgr_withPoints`). El ajuste no descarta por perfil antes del cálculo, para permitir el fallback; las restricciones se aplican en los costos.
2. `pgr_withPointsKSP` con k = `alternatives` + 1, luego descartar alternativas con > 80 % de solapamiento. En pgRouting 3.7, `points_sql` usa `pid` positivos que la función convierte internamente a identificadores virtuales negativos.
3. Si no hay ruta: relajar en este orden y recalcular, devolviendo `no_accessible_route` con `fallback_route` y la lista de restricciones violadas: (a) `avoid_unverified`, (b) `curb_ramp unknown`, (c) superficie +1, (d) pendiente +2 %. Las dos primeras relajaciones son independientes. Nunca se relajan escalones ni barreras críticas confirmadas sin decirlo explícitamente.
4. Ruta más corta de referencia: `pgr_withPoints` (Dijkstra) con `cost = length_m` sin restricciones; listar barreras que la bloquean para el perfil.

## 5. Resultado
- **Segmentos:** tramos consecutivos agrupados por estado y atributos similares.
- **accessibility_score** = 100 − (penalización suave media ponderada por longitud · 40) − 10 por cada aviso `major`, acotado a [0, 100].
- **Avisos** (`core/routing/narrative.py`): códigos estables (`slope_moderate`, `slope_steep_downhill`, `surface_irregular`, `unverified_segment`, `curb_ramp_unknown`, `narrow_passage`, `road_shoulder`) con texto i18n.
- **Instrucciones:** giros a partir del cambio de rumbo > 30° entre tramos y nombres de vía/POIs cercanos.
- **Duración** = Σ longitud / (speed_mps · factor_pendiente), con factor 0,7 en subidas > 5 %.

## 6. Pruebas obligatorias
- Grafo sintético (seed) con casos: escalera evitada, pendiente en un sentido permitida y en el otro no, cruce sin rampa, ancho insuficiente, sin ruta posible → fallback.
- Regresión por región: `region.config.regression_routes` = lista de `{origin, destination, profile, must_avoid_barrier_ids, max_distance_m}`.
- Rendimiento: 100 pares aleatorios en el campus, p95 < 800 ms.
