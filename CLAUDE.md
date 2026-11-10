# CLAUDE.md — Instrucciones para el agente programador

Estás implementando **APP-REDUC**: app móvil de rutas accesibles para sillas de ruedas con mapa de accesibilidad generado por visión por computadora. La especificación completa está en `docs/`. **La especificación manda**: si algo no está claro o crees que está mal, no improvises un diseño distinto en silencio; anota la duda en el PR y propón el cambio en `docs/`.

## Antes de empezar cualquier tarea
1. Lee `docs/09-plan-implementacion.md` y elige la siguiente tarea `T-xx` cuyas dependencias estén hechas.
2. Lee las secciones de `docs/` que la tarea referencia (p. ej. `06 §3`).
3. Trabaja en una rama `feat/T-xx-descripcion-corta`; un PR por tarea.

## Comandos
```
make up          # docker compose: db, redis, minio, api, worker, tiles, admin
make migrate     # alembic upgrade head
make seed        # región sintética de desarrollo
make test        # backend + mobile + admin
make lint        # ruff, mypy, eslint, tsc
pnpm gen:api     # regenerar packages/api-client desde OpenAPI
```
(T-01 crea estos comandos; mantenlos funcionando.)

## Reglas no negociables
- **Seguridad del usuario primero.** Nunca devolver como accesible un tramo con una barrera crítica confirmada. Ante datos faltantes, penaliza; no asumas que es accesible.
- **Nada asume el campus.** Todo pertenece a una `region`; nada de coordenadas fijas en código (solo en el seed y fixtures).
- **Una sola función de costo** (`core/routing/cost.py`) para SQL y Python, con la prueba de equivalencia.
- `core/domain` es puro: sin BD, red ni frameworks.
- Las pruebas no usan red: usa `FakeImageProvider`, `FakeDetector`, respuestas grabadas y el seed.
- No escribas a mano el cliente API de TypeScript; regéneralo.
- Todo texto de UI va por i18n en español (y clave en inglés).
- Toda pantalla nueva cumple `docs/07-app-movil.md §5` (accesibilidad).
- Respeta licencias: Street View desactivado por defecto; atribuir Mapillary y OSM.
- Secretos solo en variables de entorno; nunca en git.
- No subas imágenes, datasets ni pesos de modelos al repositorio (van a S3/MinIO).

## Definición de "hecho" para cada tarea
- Criterios de aceptación de la tarea cumplidos.
- Pruebas nuevas para la lógica añadida; `make test` y `make lint` en verde.
- Si cambiaste un contrato (API, esquema, config), actualiza el documento de `docs/` correspondiente en el mismo PR.
- Descripción del PR: tarea `T-xx`, qué se hizo, cómo probarlo, decisiones tomadas.

## Mapa de la documentación
- Qué construir: `docs/01-prd.md`
- Cómo encaja todo: `docs/02-arquitectura.md`
- Tablas: `docs/03-modelo-datos.md`
- Contratos HTTP: `docs/04-api.md`
- Visión por computadora: `docs/05-pipeline-vision.md`
- Ruteo y perfiles: `docs/06-enrutamiento.md`
- App y panel: `docs/07-app-movil.md`
- Estructura y estilo: `docs/08-estructura-y-convenciones.md`
- Tareas: `docs/09-plan-implementacion.md`
- Por qué y riesgos: `docs/10-decisiones-y-riesgos.md`
