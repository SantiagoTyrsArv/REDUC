# @reduc/api-client

Tipos y cliente TypeScript de la API, **generados** desde el OpenAPI de FastAPI.

```bash
pnpm gen:api        # exporta backend → openapi.json y regenera src/schema.d.ts
```

- `openapi.json` y `src/schema.d.ts` son artefactos generados: no se editan a mano.
- `src/index.ts` solo reexporta tipos con nombres cómodos y crea el cliente `openapi-fetch`.
- CI ejecuta `pnpm --filter @reduc/api-client check` y falla si los artefactos están desactualizados.
