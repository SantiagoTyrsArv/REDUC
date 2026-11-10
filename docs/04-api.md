# 04 — API REST

Base: `/v1` (pública) y `/v1/admin` (requiere JWT). JSON UTF-8. Coordenadas siempre `[lon, lat]` (orden GeoJSON). FastAPI genera OpenAPI en `/docs`; el cliente TypeScript de `mobile` y `admin` se **genera** desde ese OpenAPI (`packages/api-client`, con `openapi-typescript`), nunca se escribe a mano.

## 1. Errores
Formato único (RFC 9457 simplificado):
```json
{"type": "no_accessible_route", "title": "No existe una ruta accesible", "detail": "Todas las rutas cruzan escalones", "status": 422, "extra": {...}}
```
| type | status | Cuándo |
|---|---|---|
| `validation_error` | 422 | cuerpo inválido |
| `outside_region` | 422 | origen o destino fuera de toda región activa |
| `no_nearby_path` | 422 | no hay tramo peatonal a ≤ 50 m |
| `no_accessible_route` | 422 | ninguna ruta cumple las restricciones duras (incluye `extra.fallback_route`) |
| `not_found` | 404 | |
| `unauthorized` / `forbidden` | 401 / 403 | |
| `rate_limited` | 429 | > 60 rutas/min por IP |

## 2. Endpoints públicos

### `GET /v1/health`
`{"status":"ok","db":"ok","version":"0.1.0"}`

### `GET /v1/regions`
Regiones activas con versión publicada.
```json
[{"id":"…","slug":"campus-piloto","name":"Campus …","bbox":[-74.1,4.6,-74.0,4.7],
  "boundary":{GeoJSON},"map_version":{"id":"…","number":3,"published_at":"…"},
  "stats":{"edges":1830,"coverage_pct":92.4,"verified_pct":71.0}}]
```

### `GET /v1/regions/{slug}/pois?q=biblio&category=entrance&limit=20`
Búsqueda de texto (tsvector, español) + filtro. Respuesta: lista de `{id,name,category,location:[lon,lat],accessible_entrance}`.

### `GET /v1/profiles/presets`
Plantillas de perfil (ver `06-enrutamiento.md` §2).

### `POST /v1/routes`
```json
{
  "origin": [-74.0651, 4.6012],
  "destination": [-74.0632, 4.6031],
  "profile": {
    "device": "manual",
    "max_uphill_pct": 6.0,
    "max_downhill_pct": 8.0,
    "max_cross_slope_pct": 3.0,
    "max_step_cm": 2.0,
    "min_width_m": 0.9,
    "max_surface_class": 2,
    "require_curb_ramps": true,
    "avoid_unverified": false,
    "speed_mps": 0.9,
    "weights": {"slope": 1.0, "surface": 1.0, "uncertainty": 1.0}
  },
  "alternatives": 2,
  "include_shortest": true,
  "locale": "es"
}
```
Respuesta 200:
```json
{
  "region": "campus-piloto",
  "map_version": 3,
  "routes": [{
    "id": "r1",
    "geometry": {"type":"LineString","coordinates":[...]},
    "distance_m": 642.0,
    "duration_s": 713,
    "accessibility_score": 88,
    "verified_pct": 76.0,
    "max_slope_pct": 5.1,
    "segments": [{
      "edge_ids":[101,102],
      "geometry":{...},
      "distance_m":85.2,
      "status":"caution",
      "slope_pct":5.1,
      "surface_class":2,
      "warnings":[{"code":"slope_moderate","message":"Pendiente de subida del 5 % durante 40 m"}]
    }],
    "instructions":[{"distance_m":120,"text":"Gira a la derecha hacia la rampa del edificio B","maneuver":"right","location":[...]}]
  }],
  "shortest": {
    "distance_m": 410.0,
    "blocking_barriers":[{"id":"…","class":"stairs","location":[...],"message":"Escalera de 6 escalones"}]
  }
}
```

### `GET /v1/barriers/{id}`
`{id,class,severity,location,attributes,confidence,n_observations,source,verification_status,photo_url?,attribution?}`. `photo_url` es URL firmada (15 min) del recorte, solo si la licencia lo permite. Las barreras `rejected` responden 404, igual que quedan fuera de la tesela `barrier`: solo se conservan para auditoría en el panel.

### Teselas (servidas por Martin, mismo dominio bajo `/tiles`)
- `/tiles/edge_accessibility/{z}/{x}/{y}` — propiedades: `status`, `slope_pct`, `surface_class`, `verified`.
- `/tiles/barrier/{z}/{x}/{y}` — propiedades: `id`, `class`, `severity`, `verification_status`.
Ambas filtran por la versión publicada de cada región (funciones SQL en `db/tiles.sql`).

## 3. Endpoints de administración (`/v1/admin`)

| Método y ruta | Rol | Descripción |
|---|---|---|
| `POST /auth/login` | — | `{email,password}` → `{access_token,refresh_token}` |
| `POST /auth/refresh` | — | `{refresh_token}` → par nuevo; el usuario debe seguir activo |
| `GET /auth/me` | cualquiera | `{id,email,role}` del usuario autenticado |
| `GET/POST /regions` | admin | listar / crear (`slug,name,boundary,utm_srid,config`) |
| `PATCH /regions/{id}` | admin | |
| `POST /regions/{id}/pipeline-runs` | admin | `{"stages":["all"] | [...], "map_version":"new" | "<id>"}` → 202 + run |
| `GET /pipeline-runs/{id}` | admin | estado y etapas |
| `POST /pipeline-runs/{id}/cancel` | admin | |
| `POST /regions/{id}/images` | verifier | multipart; uno o varios JPEG con EXIF GPS; opcional `heading_deg` |
| `GET /review-queue?region=&class=&status=unverified&sort=priority` | verifier | barreras paginadas |
| `GET /barriers/{id}/observations` | verifier | detecciones con recortes |
| `POST /barriers/{id}/verifications` | verifier | `{"action":"confirm"|"reject"|"correct","changes":{...},"comment":""}` |
| `POST /barriers` | verifier | crear barrera manual `{class,location,attributes,image_id?}` |
| `PATCH /edges/{id}/accessibility` | verifier | sobrescribir atributos medidos en campo (p. ej. pendiente con inclinómetro) |
| `GET /map-versions?region=` | admin | |
| `POST /map-versions/{id}/publish` | admin | valida (§4) y publica |
| `GET /metrics/region/{id}` | admin | cobertura, verificados, distribución de clases, precisión estimada |

Autenticación: cabecera `Authorization: Bearer <access_token>` (HS256, 15 min; refresh 7 días). El rol se lee de la base de datos en cada petición, así que desactivar un usuario lo expulsa de inmediato, y cambiar su contraseña o rol (`app_user.token_version`) invalida todos sus tokens anteriores; `admin` incluye los permisos de `verifier`. `login` y `refresh` están limitados a 10 intentos/min por IP (`rate_limited`). Si `REDUC_JWT_SECRET` falta o tiene menos de 32 bytes, la API no emite ni acepta tokens y responde 503 `auth_unavailable`. Los usuarios se crean con `scripts/create_admin.py` (la contraseña se lee de `REDUC_ADMIN_PASSWORD` o se pide por consola; mínimo 12 caracteres).

## 4. Validaciones al publicar
- Todos los tramos tienen `edge_accessibility`.
- El grafo es conexo en ≥ 95 % de nodos (componente gigante).
- Ninguna barrera `critical` con `confidence ≥ 0.8` está sin asociar a tramo/nodo.
- Pruebas de rutas de regresión de la región (`region.config.regression_routes`) pasan.

## 5. Paginación
Cursor: `?limit=50&cursor=<opaco>` → `{"items":[...],"next_cursor":"…"|null}`.
