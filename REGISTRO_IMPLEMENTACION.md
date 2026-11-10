# Registro de implementación — APP-REDUC

## Estado al 10 de noviembre de 2026

- **T-01 a T-19 (Hitos 0, 1 y 2):** completadas; están en `main`.
- **T-20 a T-25 y MVP local:** hechas en ramas apiladas, cada una con su PR pendiente de revisión:
  `fix/seguridad-api` → `feat/T-20-importador-osm` → `feat/T-21-elevacion` → `feat/T-23-auth-admin` →
  `feat/T-22-orquestacion` → `feat/T-24-versionado` → `feat/T-25-proveedores-imagenes` → `feat/mvp-campus-pasto`.
  T-23 se adelantó a T-22 porque los endpoints de ejecuciones necesitan autenticación.
- **Backend en la punta:** ruff, formato y mypy correctos; batería completa en verde con PostGIS real (Testcontainers).
- **Comprobado con el stack de Docker real:** API → Redis → worker Dramatiq → Overpass → publicación → `POST /v1/routes`.
- **Pendiente de validación humana (Hito 2):** revisión con TalkBack/VoiceOver (`docs/07 §5.1`) y flujo Maestro.
- **Siguiente tarea del plan:** T-26 (privacidad). Quedan T-26 a T-40.

## MVP local: Universidad Cooperativa de Colombia, campus Pasto

Región `ucc-pasto` en la base de datos de desarrollo (no en el código ni en el seed):

```bash
# Dentro del contenedor api (docker compose exec -T api uv run --no-sync python ...)
scripts/create_admin.py --email <correo>          # contraseña por REDUC_ADMIN_PASSWORD
scripts/create_region.py --slug ucc-pasto --name "Universidad Cooperativa de Colombia - Campus Pasto"     --center -77.2898981 1.2297579 --radius-m 500 --elevation-path dem/ucc-pasto.tif --active
# POST /v1/admin/regions/{id}/pipeline-runs  →  POST /v1/admin/map-versions/{id}/publish
scripts/import_pois.py --slug ucc-pasto
```

- **Límite de la región:** OSM solo tiene el campus como un punto (nodo en Pandiaco), sin polígono. La región es un
  cuadrado de 1 km de lado centrado en ese punto; hay que sustituirlo por el polígono real (`--geojson`).
- **Elevación:** recorte de Copernicus GLO-30 (30 m) en `data/dem/ucc-pasto.tif` (fuera de git). Con esa resolución
  las pendientes son aproximadas y se marcan `dem_lowres`; Pasto es montañoso, así que conviene un MDE mejor o
  mediciones con inclinómetro en los tramos críticos.
- **Sin visión todavía:** no hay barreras detectadas por imágenes; las únicas barreras son las escaleras de OSM.
  Ningún tramo está verificado.
- **Resultado de la primera versión:** 819 tramos (305 inaccesibles, 123 con precaución, 391 sin datos suficientes).
- La región del seed (`campus-piloto`) se desactivó en la base de desarrollo para que la app abra en Pasto;
  `make seed` la vuelve a crear activa.
- **App Android:** `mobile/.env.local` apunta a la IP del equipo en la red local; el teléfono debe estar en la misma
  Wi-Fi y el cortafuegos de Windows debe permitir los puertos 8000 y 3000.

## Trabajo realizado

### T-01

- Estructura de `backend`, `mobile`, `admin`, `packages`, `ml`, `infra` y `.github/workflows`.
- Backend Python 3.12 con `uv`, Ruff, mypy estricto, pytest y cobertura.
- Workspace `pnpm` para `mobile`, `admin` y `packages/api-client`.
- `Makefile` con `up`, `down`, `migrate`, `seed`, `test`, `lint` y `gen:api`.
- `.env.example`, `.editorconfig`, `.gitignore` y archivos Docker ignore.
- CI inicial para backend, móvil y administración.
- Prueba inicial del paquete.

### T-02

- `docker-compose.yml` con `db`, `redis`, `minio`, `minio-init`, `api`, `worker`, `tiles` y `admin`.
- Imagen de base de datos basada en `pgrouting/pgrouting:16-3.5-3.7` con inicialización de `postgis`, `pgrouting` y `citext`.
- Imagen compartida para API y worker basada en Python 3.12 y `uv`.
- Endpoint inicial `GET /v1/health`.
- Martin conectado a PostgreSQL mediante `infra/martin.yaml`.
- Worker provisional activo hasta implementar Dramatiq en T-22.
- Panel React 18 + Vite compilado y servido mediante Nginx; la interfaz se implementará en T-32.
- Creación automática del bucket `reduc`.
- `make up` levanta los contenedores en segundo plano.

## Decisiones y problemas resueltos

- Las imágenes comunitarias originales `minio/minio` y `minio/mc` ya no están disponibles públicamente. Se usaron imágenes compatibles mantenidas por la comunidad:
  - `docker.io/pgsty/minio:RELEASE.2026-08-04T00-00-00Z`
  - `docker.io/pgsty/mc:RELEASE.2026-09-16T00-00-00Z`
- La imagen PostgreSQL 16 + PostGIS 3.4 + pgRouting 3.6 indicada originalmente ya no está disponible. Se adoptó PostgreSQL 16 + PostGIS 3.5 + pgRouting 3.7.
- Los puertos 5432 y 6379 no se publican al host: PostgreSQL y Redis son accesibles dentro de la red de Compose. Esto evitó un conflicto con el puerto 6379 ya ocupado localmente.
- Docker Desktop está instalado por usuario. En esta terminal su CLI se encuentra en `%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin\docker.exe`.
- `make` no está instalado; las validaciones se ejecutaron directamente con `uv` y `npx pnpm@10.22.0`.
- Evaluación web registrada en ADR-009: se mantiene CSR; INP y disciplina del event loop se aplicarán con la UI real desde T-32. Web Workers/`postMessage`, `SharedArrayBuffer`/`crossOriginIsolated` y WebSockets quedan condicionados a una necesidad medida; no se añade código prematuro al panel vacío.

## Verificaciones realizadas

- Ruff y formato: correctos.
- mypy: sin errores.
- pytest: 55 pruebas superadas; cobertura total del código existente: 92 %.
- Panel administrativo: compilación de producción correcta.
- `GET http://localhost:8000/v1/health` devuelve:
  `{"status":"ok","db":"ok","version":"0.1.0"}`
- Panel `http://localhost:5173/`: HTTP 200.
- MinIO `http://localhost:9000/minio/health/live`: HTTP 200.
- Martin `http://localhost:3000/catalog`: HTTP 200.
- Base de datos: PostGIS 3.5 y pgRouting 3.7.3 verificados.
- Bucket `reduc`: acceso autenticado verificado.

## Comandos útiles en este equipo

Desde Git Bash en la raíz del proyecto:

```bash
export PATH="$LOCALAPPDATA/Programs/DockerDesktop/resources/bin:$PATH"
docker compose ps --all
docker compose up --build --detach
docker compose down
```

Validaciones sin `make`:

```bash
uv sync --directory backend
uv run --directory backend ruff check .
uv run --directory backend ruff format --check .
uv run --directory backend mypy
uv run --directory backend pytest
npx --yes pnpm@10.22.0 install
npx --yes pnpm@10.22.0 --recursive --if-present lint
npx --yes pnpm@10.22.0 --recursive --if-present test
```

## Cambios de T-03

- Configuración centralizada en `backend/src/reduc/settings.py` con prefijo `REDUC_`.
- Errores uniformes `validation_error`, `not_found`, `unauthorized`, `forbidden` y `rate_limited` según `docs/04-api.md`.
- Logs JSON estructurados sin cuerpos de solicitud ni coordenadas exactas.
- Métricas Prometheus en `/metrics` y CORS configurable.
- Limitador atómico con Redis para 60 solicitudes `POST /v1/routes` por IP y minuto; respuesta 429 con `Retry-After: 60`.
- `/v1/health` comprueba PostgreSQL y devuelve `degraded`/`unavailable` si no está accesible.
- Pruebas sin servicios externos usando dobles; 7 pruebas y 85 % de cobertura total en el código actual.

## Cambios de T-04

- Alembic configurado con `REDUC_DATABASE_URL`; archivos incluidos en las imágenes Docker.
- Modelos SQLAlchemy/GeoAlchemy2 para región, versión, grafo, accesibilidad, imágenes, detecciones, barreras, verificaciones, POIs, usuarios y ejecuciones.
- Migración `20261109_0001_initial_schema.py`: 13 tablas, índices obligatorios, claves y restricciones, y vista materializada `routing_edge`.
- `poi.search_vector` es una columna generada en español con índice GIN.
- Prueba con Testcontainers y `pgrouting/pgrouting:16-3.5-3.7`: upgrade, downgrade, segundo upgrade, inserción/lectura de todas las entidades y refresco de `routing_edge`.
- Migración aplicada a la base de desarrollo; 17 tablas internas visibles incluyendo las de Alembic y extensiones, y API saludable.
- Para pruebas Docker desde Git Bash, exportar antes `%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin` en `PATH` para el helper de credenciales.

## Cambios de T-05

- Seed idempotente en `backend/scripts/seed_dev.py` para la región `campus-piloto`, versión publicada 1.
- Cuadrícula sintética 6×6 con 36 nodos, 60 tramos y 60 registros de accesibilidad.
- Tres barreras representadas: escalera, pendiente del 12 % y cruce sin rampa; cuatro POIs incluidos.
- Cada ejecución elimina y reemplaza la región sintética sin acumular duplicados, y refresca la vista `routing_edge`.
- Prueba aislada con Testcontainers para comprobar contenido e idempotencia.
- Ejecución real verificada con `docker compose exec -T api uv run --no-sync python scripts/seed_dev.py`; resultado: `seed_completed barriers=3 edges=60 nodes=36 pois=4 region=campus-piloto`.
- Consulta posterior en desarrollo: `nodes=36, edges=60, accessibility=60, barriers=3, pois=4, routing_edges=60`.
- Validación final completa: Ruff, formato y mypy correctos; 9 pruebas superadas y 93 % de cobertura total.

## Cambios de T-06

- `core/domain/profile.py`: `MobilityProfile` y `Weights` inmutables y validados, con los cuatro presets de la especificación.
- `core/routing/cost.py`: costo Python por sentido y generador `build_cost_sql(profile)` parametrizado para `cost` y `reverse_cost`.
- Restricciones duras para escalones, pendientes longitudinal y transversal, ancho, superficie, obstáculos, rampas, datos no verificados y barreras críticas confirmadas.
- Las barreras críticas confirmadas se bloquean siempre; no se añadió una tolerancia que debilite la regla de seguridad. La consulta SQL considera barreras asociadas al tramo o a sus extremos.
- Penalizaciones suaves de pendiente, superficie, obstáculos, arcén/acera faltante, incertidumbre y rampa desconocida; una altura desconocida bloquea cuando sí hay escalones.
- Hypothesis añadido al grupo de desarrollo. La propuesta de equivalencia ejecuta 100 casos sobre perfiles y tramos arbitrarios en ambos sentidos.
- Pruebas unitarias de cada restricción dura, cambios de sentido y penalizaciones. Cobertura de `core/routing/cost.py`: 100 %; `core/domain/profile.py`: 96 %.
- SQL generado ejecutado correctamente en PostgreSQL sobre los 60 tramos del seed de desarrollo.
- `docs/06-enrutamiento.md` actualizado con el límite transversal y la ausencia de tolerancia a barreras críticas en el perfil actual.
- Validación final completa: Ruff, formato y mypy correctos; 48 pruebas superadas y 94 % de cobertura total.

## Cambios de T-07

- Contrato `RoutingEngine` en `core/routing/engine.py` con coordenadas validadas, rutas, resultado y error `NoNearbyPathError` para ajustes superiores a 50 m.
- Implementación `PgrRoutingEngine` en `core/routing/pgrouting.py`: ajuste a tramos, división virtual, `pgr_withPointsKSP` y referencia con `pgr_withPoints`.
- Subgrafo por bbox calculado en el SRID UTM de la región con margen de 500 m o 30 % de la distancia, y reintento con la región completa.
- Alternativas filtradas por más de 80 % de solapamiento. La ruta más corta sin restricciones identifica sus barreras críticas confirmadas.
- Fallback acumulativo y ordenado: datos no verificados, rampa desconocida, superficie +1 y pendientes ±2 %. Las dos primeras relajaciones tienen indicadores independientes para conservar el orden.
- Escalones, barreras críticas confirmadas, rampas inexistentes, ancho insuficiente y obstáculos bloqueantes nunca se relajan.
- pgRouting 3.7 exige `pid` positivos dentro de `points_sql`; los identificadores de inicio/destino siguen siendo `-1` y `-2`. Los extremos se mantienen a una fracción mínima para conservar la división virtual.
- Siete pruebas con Testcontainers sobre el seed: los cinco casos obligatorios, protección explícita de barreras críticas y fallback independiente de rampa desconocida.
- La equivalencia Python–SQL con Hypothesis también cubre los indicadores de fallback. Cobertura de `pgrouting.py`: 90 %.
- `docs/06-enrutamiento.md` actualizado con los detalles verificados de puntos virtuales, referencia y fallback.
- Validación final completa: Ruff, formato y mypy correctos; 55 pruebas superadas y 92 % de cobertura total.

## Para reanudar

1. Fusionar los PR apilados en orden (cada uno con commit de fusión para conservar un commit por tarea).
2. Seguir con T-26 (`docs/09`): desenfoque de rostros/matrículas y limpieza de EXIF en las subidas.
