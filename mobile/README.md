# REDUC — app móvil

Expo (development build) + expo-router + MapLibre. Especificación: `docs/07-app-movil.md`.

## Desarrollo

```bash
make up && make migrate && make seed          # API en :8000, teselas en :3000
cp mobile/.env.example mobile/.env.local      # opcional; hay valores por defecto para local
pnpm --filter @reduc/mobile web               # navegador (MapLibre GL JS)
pnpm --filter @reduc/mobile android           # development build (MapLibre Native)
```

En **Ajustes → Ubicación de demostración** la app te sitúa dentro de la región activa, de modo
que el flujo completo (ruta + navegación simulada) se puede probar desde cualquier lugar.

## Pruebas

```bash
pnpm --filter @reduc/mobile lint              # tsc --noEmit
pnpm --filter @reduc/mobile test              # Jest + Testing Library, sin red
maestro test mobile/e2e/calcular-ruta.yaml    # E2E sobre un development build y el seed
```

## Estructura

- `app/`: rutas de expo-router (una por pantalla de `docs/07 §2`).
- `src/features/map`: `MapCanvas` (nativo) y `MapCanvas.web` comparten capas (`layers.ts`) y datos (`data.ts`).
- `src/features/navigation`: progreso puro (`progress.ts`) y sesión con recálculo (`useNavigationSession.ts`).
- `src/stores`: zustand persistido en MMKV (perfiles, lugares, ajustes) y estado del viaje.
- `src/i18n`: `es` (fuente) y `en`; una prueba verifica que tienen las mismas claves.

## Accesibilidad (docs/07 §5)

Checklist manual con TalkBack/VoiceOver antes de publicar un build: `docs/07-app-movil.md §5.1`.
