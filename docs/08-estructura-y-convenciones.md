# 08 — Estructura del repositorio y convenciones

## 1. Monorepo

```
app-reduc/
├── CLAUDE.md / AGENTS.md
├── README.md
├── docker-compose.yml
├── .env.example
├── Makefile                      # atajos: make up, make test, make lint, make migrate, make seed
├── docs/                         # esta especificación + ADRs
├── backend/                      # proyecto Python único (uv), dos puntos de entrada
│   ├── pyproject.toml
│   ├── alembic/                  # migraciones
│   ├── src/reduc/
│   │   ├── core/                 # domain/, db/, providers/, vision/, routing/, pipeline/ (ver 02 §4)
│   │   ├── api/                  # FastAPI: main.py, routers/, schemas/, deps.py, errors.py
│   │   ├── worker/               # main.py (Dramatiq), actors por etapa
│   │   └── settings.py           # pydantic-settings
│   ├── db/tiles.sql              # funciones para Martin
│   ├── scripts/                  # seed_dev.py, create_admin.py, export_regression.py
│   └── tests/
│       ├── unit/                 # sin BD
│       ├── integration/          # con PostGIS (testcontainers)
│       └── fixtures/             # imágenes y grafos sintéticos
├── ml/                           # entrenamiento y evaluación (no se despliega)
│   ├── datasets/README.md        # cómo obtener/anotar datos (no subir imágenes a git)
│   ├── train_detector.py, train_surface.py, eval.py
│   └── model_cards/
├── mobile/                       # Expo
│   ├── app/                      # rutas expo-router
│   ├── src/{components,features,stores,lib,i18n,theme}/
│   └── e2e/                      # Maestro
├── admin/                        # React + Vite
│   └── src/{pages,components,lib}/
├── packages/
│   └── api-client/               # tipos y cliente generados desde OpenAPI
├── infra/
│   ├── martin.yaml
│   ├── Caddyfile
│   └── deploy.md
└── .github/workflows/            # ci-backend.yml, ci-mobile.yml, ci-admin.yml
```

JS/TS: workspace **pnpm** (`mobile`, `admin`, `packages/*`). Python: **uv**.

## 2. Convenciones Python
- Python 3.12, tipado completo, `mypy --strict` en `core/`.
- Formato y lint: `ruff format` + `ruff check` (reglas E, F, I, B, UP, SIM, RUF).
- `core/domain` no importa SQLAlchemy, FastAPI ni librerías de red: lógica pura y probada.
- Repositorios (`core/db/repositories/`) encapsulan las consultas; los routers no escriben SQL.
- SQL espacial complejo en archivos `.sql` o con `text()` parametrizado; nunca concatenar entradas del usuario.
- Errores de dominio como excepciones propias mapeadas a respuestas en `api/errors.py`.
- Logs con `structlog`, nunca `print`.
- Configuración solo vía `settings.py` (variables de entorno con prefijo `REDUC_`).

## 3. Convenciones TypeScript
- `strict: true`, sin `any` (salvo justificado con comentario).
- ESLint + Prettier; componentes funcionales; hooks por funcionalidad en `src/features/<feature>/`.
- Textos de UI siempre por i18n (`t('route.summary.distance')`), nunca literales.
- No editar a mano `packages/api-client`: regenerar con `pnpm gen:api`.

## 4. Pruebas
| Capa | Herramienta | Mínimo |
|---|---|---|
| Dominio (costo, fusión, atributos, geolocalización) | pytest + Hypothesis | 90 % cobertura |
| API e integración con PostGIS | pytest + testcontainers (`pgrouting/pgrouting:16-3.5-3.7`) | todos los endpoints |
| Pipeline | pytest con fixtures sintéticas y `FakeDetector` / `FakeImageProvider` | una ejecución completa sobre la región seed |
| Mobile | Jest + Testing Library; Maestro E2E del flujo "calcular ruta" | pantallas principales |
| Admin | Vitest + Testing Library | cola de verificación |

Las pruebas **no** llaman a Mapillary, Overpass ni descargan modelos: usar dobles. Pruebas que requieran red llevan la marca `@pytest.mark.external` y no corren en CI.

## 5. Git y CI
- Rama principal `main` protegida; ramas `feat/…`, `fix/…`, `docs/…`.
- Commits convencionales (`feat(routing): …`).
- Un PR por tarea del plan (`docs/09`), con referencia a su ID (`T-07`).
- CI: lint + tipos + pruebas para cada paquete afectado; build de `mobile` con `expo export` como verificación.

## 6. Variables de entorno (`.env.example`)
```
REDUC_DATABASE_URL=postgresql+psycopg://reduc:reduc@db:5432/reduc
REDUC_REDIS_URL=redis://redis:6379/0
REDUC_S3_ENDPOINT=http://minio:9000
REDUC_S3_BUCKET=reduc
REDUC_S3_ACCESS_KEY=...
REDUC_S3_SECRET_KEY=...
REDUC_JWT_SECRET=...
REDUC_MAPILLARY_TOKEN=...
REDUC_STREETVIEW_API_KEY=            # vacío = desactivado
REDUC_MODEL_DETECTOR_VERSION=det-v0.1.0
REDUC_MODEL_SURFACE_VERSION=surf-v0.1.0
REDUC_CORS_ORIGINS=http://localhost:5173
EXPO_PUBLIC_API_URL=http://localhost:8000
EXPO_PUBLIC_TILES_URL=http://localhost:3000
EXPO_PUBLIC_MAP_STYLE_URL=...
```
