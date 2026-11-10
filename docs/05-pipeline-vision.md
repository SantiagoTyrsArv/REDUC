# 05 — Pipeline de visión por computadora

Objetivo: convertir imágenes de calle en **barreras geolocalizadas con confianza**, asociadas al grafo peatonal.

## 1. Etapas

| # | Etapa | Entrada | Salida |
|---|---|---|---|
| 1 | `import_osm` | polígono | `node`, `edge` |
| 2 | `elevation` | MDE + tramos | `node.elevation_m`, pendiente por tramo |
| 3 | `ingest_images` | proveedores | `image` (+ archivo en S3) |
| 4 | `detect` | imágenes | `detection` (bbox, clase, score, máscara) |
| 5 | `geolocate` | detecciones + pose de cámara | `detection.geom`, `geo_error_m` |
| 6 | `fuse` | detecciones geolocalizadas | `barrier` |
| 7 | `compute_attributes` | OSM + MDE + barreras + verificaciones | `edge_accessibility` |
| 8 | `build_routing_graph` | lo anterior | `routing_edge` |

Cada etapa: función pura `run(stage_ctx) -> StageStats`, idempotente (borra/reescribe sus salidas para la `map_version` en borrador), procesa en lotes de 500 y reporta progreso.

Orquestación (`core/pipeline/jobs.py`): cada etapa corre en su propia transacción; si falla o se cancela, el borrador queda como lo dejó la etapa anterior y la ejecución puede relanzarse desde ahí (`stages` + `map_version` existente). Una ejecución fallida no se reintenta sola. Las dependencias externas (OSM, elevación, imágenes, detector) llegan por `PipelineDeps`; `pipeline/wiring.py` las elige según `region.config` y las pruebas pasan dobles.

## 2. Importación OSM (etapa 1)
- Consulta Overpass (o archivo `.osm.pbf` local) con `highway IN (footway, path, pedestrian, steps, living_street, residential, service, tertiary, secondary, primary, unclassified, corridor)`, `footway=sidewalk|crossing`, `sidewalk=*`, `kerb=*`, `elevator`, `ramp`, `incline`, `surface`, `smoothness`, `width`, `wheelchair`.
- Si una calle no tiene aceras mapeadas como vías separadas, generar tramo peatonal sobre el eje con `kind='road_shoulder'` y penalización (ver ruteo).
- Partir vías en cada intersección; tramos máximos de 50 m (subdividir) para que las barreras puedan ubicarse con precisión.
- `highway=steps` → `has_steps=true`, `kind='steps'`.

## 3. Elevación (etapa 2)
- `ElevationSource.sample(points) -> elevations`. Implementación por defecto: GeoTIFF local (rasterio). Para el campus se recomienda un MDE de alta resolución (LiDAR/fotogrametría con dron ≤ 1 m); SRTM 30 m solo como último recurso (marca `data_confidence` baja en pendientes).
- Muestrear cada 5 m sobre el tramo, suavizar (mediana móvil de 3), calcular `slope_pct` global y `max_slope_pct` en ventana de 10 m.
- La etiqueta OSM `incline` y las mediciones de campo (`PATCH /edges/{id}/accessibility`) **tienen prioridad** sobre el MDE.

## 4. Ingesta de imágenes (etapa 3)

Interfaz:
```python
class ImageProvider(Protocol):
    name: str
    def list_images(self, boundary: MultiPolygon, since: datetime | None) -> Iterator[ImageMeta]: ...
    def fetch(self, meta: ImageMeta) -> bytes: ...
    def can_store(self) -> bool: ...  # según licencia
```
- **Mapillary (principal, por defecto):** API v4 (`graph.mapillary.com/images?bbox=...&fields=id,captured_at,computed_geometry,computed_compass_angle,camera_type,thumb_2048_url,creator`). Usar `computed_*` (posición y rumbo corregidos por SfM). Partir el polígono en celdas de ≤ 0,01° para respetar límites. Licencia CC BY-SA 4.0 → se puede almacenar y se debe atribuir al autor. Las imágenes ya vienen con rostros/matrículas desenfocados.
- **Upload (fotos propias):** EXIF obligatorio con GPS; rumbo de `GPSImgDirection` o campo manual; `privacy.py` desenfoca rostros y matrículas antes de guardar.
- **Street View (opcional, desactivado por defecto):** los Términos de Google Maps Platform restringen almacenar contenido y crear bases de datos derivadas. Solo se habilita si el equipo confirma un acuerdo/licencia que lo permita. Ver ADR-006.
- Panorámicas 360° (Mapillary `spherical`): reproyectar a 4 vistas perspectiva (FOV 90°) a izquierda/derecha/adelante/atrás antes de detectar.
- Deduplicar: si dos imágenes están a < 3 m y < 20° de rumbo, conservar la más reciente.
- Implementación (`core/providers/images/`, etapa `ingest_images`): las imágenes pertenecen a la región, no a la versión, así que cada ejecución solo descarga lo nuevo (`UNIQUE(provider, external_id)`); una descarga fallida no detiene la etapa y se reintenta en la siguiente. Cada panorámica se guarda como cuatro filas `image` con `external_id = "<id>:front|right|back|left"`, FOV 90° y el rumbo ya girado, de modo que detección y geolocalización solo ven vistas en perspectiva. Si la licencia no permite almacenar (`can_store() = false`), no hay `storage_key` y los bytes solo existen durante esa ejecución. Con `max_images` se conservan las más recientes. Mapillary: una celda que devuelve una página completa (2 000) se divide en cuatro; el token viaja en la cabecera `Authorization`, y las miniaturas solo se descargan por HTTPS desde hosts de Mapillary.

## 5. Taxonomía de detección

| Clase | Severidad por defecto | Notas |
|---|---|---|
| `stairs` | critical | atributo `step_count` estimado |
| `single_step` | critical si > 2 cm (estimado) | escalón aislado/desnivel en acera |
| `curb_no_ramp` | critical | bordillo en esquina/cruce sin rampa |
| `curb_ramp` | — (positivo) | rampa de bordillo presente |
| `ramp` | — (positivo) | rampa de acceso |
| `obstacle` | major | poste, árbol, vehículo, mobiliario que estrecha la acera |
| `surface_damage` | major | grietas grandes, huecos, baldosas levantadas |
| `steep_slope_visual` | minor | indicio visual; la pendiente real viene del MDE |
| `no_sidewalk` | major | |
| `narrow_sidewalk` | major | ancho libre estimado < 0,9 m |

Además, segmentación semántica por píxel de `sidewalk`, `road`, `curb`, `terrain`, `vegetation` para estimar ancho libre y tipo de superficie.

## 6. Modelos

Interfaz:
```python
class Detector(Protocol):
    version: str
    classes: list[str]
    def predict(self, images: list[np.ndarray]) -> list[list[RawDetection]]: ...
```
- **Detector de objetos:** RT-DETR (Hugging Face Transformers, licencia Apache-2.0) o YOLO (Ultralytics, **AGPL-3.0** — aceptable en proyecto académico de código abierto; evaluar antes de uso comercial). Partir de pesos preentrenados en COCO y afinar.
- **Segmentación:** SegFormer o Mask2Former preentrenado en **Mapillary Vistas** / Cityscapes (incluye `sidewalk`, `curb`, `curb-cut`).
- **Clasificador de superficie:** clasificador ligero (EfficientNet/ConvNeXt-T) sobre recortes de acera → `surface_class` 0–4.
- **Datos de entrenamiento:**
  - Project Sidewalk (Universidad de Washington): etiquetas de curb ramp, missing curb ramp, obstacle, surface problem sobre Street View (revisar licencia de imágenes; usar las etiquetas para entrenar es investigación).
  - Mapillary Vistas (segmentación).
  - **Conjunto propio del campus:** ≥ 1 500 fotos anotadas (CVAT o Label Studio), dividido 70/15/15 por zona geográfica (no aleatorio) para evitar fuga.
- Los pesos se guardan en S3 `models/{name}/{version}/` con un `model_card.md` (datos, métricas, fecha). El worker carga la versión indicada en `MODEL_DETECTOR_VERSION`.
- Entrenamiento en `ml/` (notebooks + scripts), separado del worker de producción. El worker solo hace inferencia.

## 7. Geolocalización (etapa 5)
Para cada detección:
1. Rumbo del objeto: `bearing = heading + ((x_center / width) − 0.5) · fov` (vista perspectiva).
2. Distancia: con la base del bbox `y_bottom` y la altura de cámara `h`, asumiendo suelo plano: `ángulo_depresión = pitch + ((y_bottom/height) − 0.5)·fov_v`; `d = h / tan(ángulo_depresión)`, recortada a [1 m, 25 m]. Si la segmentación da contacto con el suelo, usarlo.
3. Punto estimado = destino geodésico desde la cámara con `bearing` y `d` (pyproj `Geod`).
4. `geo_error_m` = f(d) (≈ 0,15·d + error GPS de la fuente: Mapillary computed ≈ 2 m; móvil ≈ 5 m).
5. Asociación al grafo: barreras de nodo (`curb_no_ramp`, `curb_ramp`) → nodo `crossing`/`curb` más cercano ≤ `snap_max_m`; resto → tramo más cercano cuyo rumbo sea compatible y esté del lado visible. Si no hay candidato, `edge_id = null` (queda en la cola de revisión).

## 8. Fusión (etapa 6)
- Agrupar detecciones de la misma clase con DBSCAN (`eps = fusion_radius_m`, `min_samples = 1`) en coordenadas UTM.
- Posición = media ponderada por `score / geo_error_m²`.
- Confianza agregada: `1 − Π(1 − score_i · w_i)`, con `w_i` = calidad de imagen (0,5–1). Si la zona fue fotografiada ≥ 3 veces y solo 1 imagen detecta la barrera, multiplicar por 0,6 (evidencia negativa).
- Barreras de OSM (`highway=steps`, `kerb=raised`) entran con `source='osm'` y confianza 0,7.
- **Las verificaciones humanas sobrescriben**: `confirmed` → confianza 1,0; `rejected` → la barrera no afecta al ruteo pero se conserva para auditoría. Al regenerar una versión, las verificaciones se transfieren por proximidad (≤ 3 m, misma clase).

## 9. Atributos de tramo (etapa 7)
Reglas (en `core/domain/attributes.py`, con pruebas unitarias por regla):
- `has_steps` = `kind='steps'` ∨ barrera `stairs`/`single_step` con confianza ≥ 0,5 no rechazada.
- `curb_ramp_start/end`: por nodo extremo de tramos `crossing`: `yes` si hay `curb_ramp` o `kerb=lowered|flush`; `no` si `curb_no_ramp` o `kerb=raised`; si no, `unknown`.
- `surface_class` = máximo entre OSM (`surface`/`smoothness` mapeado) y percentil 75 del clasificador; `surface_damage` sube un nivel.
- `obstacle_level`, `width_m`, `sidewalk_missing` según barreras y segmentación.
- `data_confidence` = mínimo de las confianzas relevantes; 0,3 si `coverage='osm_only'`; 0,1 si `none`.
- `status` (para la capa visual) con el perfil "manual estándar".

## 10. Evaluación
- Script `ml/eval.py` sobre el conjunto de prueba del campus: precisión, recall, mAP@0.5 por clase; matriz de confusión.
- Evaluación geográfica: 100 barreras medidas en campo con GPS de precisión → error mediano de posición (meta < 5 m).
- Evaluación de extremo a extremo: 30 rutas de regresión definidas por el equipo con resultado esperado (p. ej. "no debe pasar por la escalera del edificio C").
- Cada nueva versión del modelo debe igualar o mejorar recall de `stairs` y `curb_no_ramp` antes de usarse.
