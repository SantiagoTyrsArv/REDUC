# 09 — Plan de implementación

Cada tarea es un PR. No empezar una tarea hasta que sus dependencias estén terminadas. "Hecho" = criterios de aceptación cumplidos + pruebas + lint en verde + documentación actualizada si cambió un contrato.

## Hito 0 — Base del proyecto

**T-01 Estructura del monorepo.** Crear la estructura de `08 §1`, `pyproject.toml` (uv), workspace pnpm, Makefile, `.env.example`, `.editorconfig`, CI vacío que pase.
*Acepta:* `make lint` y `make test` corren sin errores en un repo limpio.

**T-02 Docker Compose.** Servicios `db` (`pgrouting/pgrouting:16-3.5-3.7`), `redis`, `minio` compatible con S3 (+ creación del bucket), `api`, `worker`, `tiles` (Martin), `admin`.
*Acepta:* `make up` levanta todo; `GET /v1/health` responde `ok`.

**T-03 Esqueleto FastAPI + settings + errores + logs.** Formato de error de `04 §1`, `/v1/health`, `/metrics`, CORS, limitador de tasa.
*Depende:* T-02.

**T-04 Esquema de BD y migraciones.** Todas las tablas e índices de `03`, extensiones `postgis`, `pgrouting`, `citext`. Modelos SQLAlchemy/GeoAlchemy2.
*Acepta:* `alembic upgrade head` y `downgrade base` funcionan; prueba de integración crea y lee cada entidad.

**T-05 Seed sintético.** `scripts/seed_dev.py` con la región cuadrícula de `03 §6`, incluyendo `edge_accessibility` y POIs.
*Depende:* T-04.

## Hito 1 — Ruteo (valor de usuario temprano con datos sintéticos/OSM)

**T-06 Dominio de perfiles y costo.** `MobilityProfile`, presets, `cost.py` (Python + generador SQL), prueba de equivalencia con Hypothesis.
*Acepta:* pruebas unitarias de cada restricción dura de `06 §3`.

**T-07 RoutingEngine con pgRouting.** `pgr_withPoints` + `pgr_KSP`, subgrafo por bbox, ruta más corta de referencia, fallback con relajación.
*Acepta:* los 5 casos de `06 §6` pasan sobre el seed.

**T-08 Narrativa y puntuación.** Segmentación, avisos, instrucciones, puntuación, duración; textos i18n `es`/`en`.

**T-09 Endpoints públicos.** `/v1/regions`, `/v1/regions/{slug}/pois`, `/v1/profiles/presets`, `/v1/routes`, `/v1/barriers/{id}`.
*Acepta:* pruebas de integración de cada endpoint y de cada error de `04 §1`. OpenAPI publicado.

**T-10 Teselas vectoriales.** `db/tiles.sql` (funciones filtrando versión publicada) + `infra/martin.yaml`.
*Acepta:* `/tiles/edge_accessibility/15/x/y` devuelve MVT con propiedades correctas sobre el seed.

**T-11 Cliente API generado.** `packages/api-client` con `openapi-typescript` + `openapi-fetch`; script `pnpm gen:api`; CI falla si está desactualizado.

## Hito 2 — App móvil MVP

**T-12 Base de la app.** Expo + expo-router + i18n + tema (claro/oscuro, contraste) + stores persistidos + React Query.
**T-13 Mapa principal y capa de accesibilidad** (`07 §4`) con leyenda.
**T-14 Onboarding y perfiles** (crear desde plantilla, editar, activo).
**T-15 Búsqueda** (POIs, favoritos, recientes, elegir en el mapa).
**T-16 Planificación de ruta** (resumen, alternativas, comparación con la más corta, avisos, lista de segmentos accesible, manejo de `no_accessible_route`).
**T-17 Detalle de barrera.**
**T-18 Navegación básica** (seguimiento, instrucción actual, recálculo > 25 m).
**T-19 Accesibilidad y E2E.** Revisión con TalkBack/VoiceOver según `07 §5`; flujo Maestro "abrir app → elegir destino → ver ruta".
*Acepta del hito:* con el seed, un usuario puede calcular una ruta que evita la escalera y entender por qué solo con lector de pantalla.

## Hito 3 — Datos reales del campus

**T-20 Importador OSM** (`05 §2`): Overpass/pbf → nodos/tramos, subdivisión ≤ 50 m, aceras sintéticas `road_shoulder`.
*Acepta:* sobre un .pbf de prueba incluido en fixtures, el número de tramos y la topología coinciden con lo esperado.
**T-21 Elevación** (`ElevationSource` GeoTIFF + cálculo de pendientes). Prueba con un raster sintético inclinado.
**T-22 Orquestación del pipeline.** Dramatiq, `pipeline_run`/`pipeline_stage_run`, idempotencia, progreso, cancelación, endpoints admin de ejecuciones.
**T-23 Autenticación admin** (JWT, roles, `scripts/create_admin.py`).
**T-24 Versionado y publicación del mapa** con validaciones de `04 §4`.

## Hito 4 — Visión por computadora

**T-25 Proveedores de imágenes.** `MapillaryProvider` (paginación por celdas, dedupe, panorámicas → 4 vistas), `UploadProvider` (EXIF), `StreetViewProvider` detrás de bandera desactivada. Pruebas con respuestas grabadas (sin red).
**T-26 Privacidad.** Desenfoque de rostros/matrículas en subidas (detector ligero, p. ej. modelo de rostros + matrículas) y limpieza de EXIF.
**T-27 Interfaz Detector + FakeDetector + inferencia real.** Carga de pesos desde S3 por versión; procesamiento por lotes; guarda recortes.
**T-28 Geolocalización** (`05 §7`) con pruebas geométricas deterministas (cámara y objeto conocidos → error < 0,5 m en suelo plano).
**T-29 Fusión** (`05 §8`) con pruebas: varias observaciones → una barrera, evidencia negativa, transferencia de verificaciones.
**T-30 Cálculo de atributos** (`05 §9`), una prueba por regla.
**T-31 `ml/`: entrenamiento y evaluación.** Scripts de entrenamiento del detector y del clasificador de superficie, `eval.py`, `model_card` de la primera versión. (Requiere el conjunto anotado del campus: ver preguntas abiertas.)

## Hito 5 — Panel de verificación

**T-32 Admin web base** (login, layout, mapa).
**T-33 Regiones y ejecuciones** (crear región, lanzar pipeline, ver progreso).
**T-34 Cola de verificación** con atajos de teclado y endpoints `review-queue`, `verifications`, `barriers` manuales, `PATCH edges`.
**T-35 Subida de fotos propias** y versiones/publicación con diferencias.
**T-36 Métricas de región.**

## Hito 6 — Piloto

**T-37 Rutas de regresión del campus** y prueba de rendimiento (p95 < 800 ms).
**T-38 Despliegue** en VM con Caddy + backups diarios de PostgreSQL; `infra/deploy.md`.
**T-39 Builds EAS** (Android interno, iOS TestFlight).
**T-40 Documentación de operación:** cómo añadir una región nueva paso a paso (demuestra RNF-09).

## Orden sugerido y paralelismo
```
T-01 → T-02 → T-03 → T-04 → T-05
                         ├→ T-06 → T-07 → T-08 → T-09 → T-11 → T-12..T-19
                         ├→ T-10
                         └→ T-20 → T-21 → T-22 → T-23 → T-24 → T-25..T-31 → T-32..T-36 → T-37..T-40
```
La app (hito 2) y el pipeline (hitos 3-4) pueden avanzar en paralelo una vez cerrado T-11.
