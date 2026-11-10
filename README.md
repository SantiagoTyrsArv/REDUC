# APP-REDUC — Rutas accesibles para personas en silla de ruedas

Aplicación móvil que calcula rutas accesibles para personas en silla de ruedas usando un **mapa de accesibilidad generado automáticamente con visión por computadora** a partir de imágenes de nivel de calle (Mapillary, fotografías propias del campus y, opcionalmente, Street View). Las rutas priorizan la accesibilidad sobre la distancia y se ajustan al **perfil de movilidad** de cada usuario.

Piloto: campus universitario. Diseño: extensible a cualquier zona geográfica ("región") sin cambiar la arquitectura, solo procesando las imágenes de esa zona.

> La implementación sigue `CLAUDE.md` y `docs/09-plan-implementacion.md`. La base del monorepo (T-01) y los servicios locales (T-02) están configurados; los módulos restantes se completarán en el orden del plan.

## Desarrollo

Requisitos: Python 3.12, `uv`, Node.js 22+, `pnpm` 10 y `make`.

```bash
corepack enable
pnpm install
uv sync --directory backend
make lint
make test
```

Con Docker instalado y el daemon en ejecución, `make up` levanta la base de datos, Redis, MinIO, la API, el worker, Martin y el panel. La API queda en `http://localhost:8000/v1/health`; la consola de MinIO, en `http://localhost:9001`.

Las migraciones y el seed se habilitan en T-04 y T-05.

## Índice de documentación

| # | Documento | Contenido |
|---|-----------|-----------|
| — | [CLAUDE.md](CLAUDE.md) / [AGENTS.md](AGENTS.md) | Reglas para el agente programador (léelo primero) |
| 01 | [PRD / Requisitos](docs/01-prd.md) | Visión, usuarios, casos de uso, requisitos funcionales y no funcionales, alcance MVP |
| 02 | [Arquitectura](docs/02-arquitectura.md) | Contexto, contenedores, componentes, flujos, stack, despliegue |
| 03 | [Modelo de datos](docs/03-modelo-datos.md) | Esquema PostgreSQL/PostGIS completo |
| 04 | [API REST](docs/04-api.md) | Endpoints, contratos, errores |
| 05 | [Pipeline de visión](docs/05-pipeline-vision.md) | Ingesta de imágenes, detección, geolocalización, fusión, evaluación |
| 06 | [Motor de rutas](docs/06-enrutamiento.md) | Grafo peatonal, perfiles, función de costo, algoritmo |
| 07 | [App móvil](docs/07-app-movil.md) | Pantallas, navegación, estado, accesibilidad de la propia UI |
| 08 | [Estructura y convenciones](docs/08-estructura-y-convenciones.md) | Monorepo, estilo de código, pruebas, git |
| 09 | [Plan de implementación](docs/09-plan-implementacion.md) | Tareas ordenadas con criterios de aceptación |
| 10 | [Decisiones y riesgos](docs/10-decisiones-y-riesgos.md) | ADRs, riesgos, preguntas abiertas |

## Stack resumido

- **App móvil:** React Native + Expo (TypeScript), MapLibre.
- **Backend API:** Python 3.12 + FastAPI.
- **Datos:** PostgreSQL 16 + PostGIS + pgRouting; Redis; almacenamiento S3 (MinIO en local).
- **Visión:** worker Python (PyTorch) con detector de objetos + segmentación, cola de trabajos.
- **Panel de administración/verificación:** React + Vite (web).
- **Infra local:** Docker Compose.
