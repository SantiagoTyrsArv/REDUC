# 07 — App móvil

Expo (SDK estable más reciente, *development build* porque MapLibre requiere código nativo), TypeScript estricto, Expo Router.

## 1. Librerías
| Uso | Librería |
|---|---|
| Navegación | `expo-router` |
| Mapa | `@maplibre/maplibre-react-native` |
| Ubicación | `expo-location` |
| Datos remotos | `@tanstack/react-query` + cliente generado de `packages/api-client` |
| Estado local | `zustand` con persistencia en `react-native-mmkv` |
| i18n | `i18next` + `react-i18next` (`es` por defecto, `en`) |
| Voz (fase 2) | `expo-speech` |
| Pruebas | Jest + `@testing-library/react-native`; Maestro para E2E |

Mapa base: estilo MapLibre de un proveedor con plan gratuito (p. ej. OpenFreeMap o MapTiler), configurable por `EXPO_PUBLIC_MAP_STYLE_URL`. Atribuir © OpenStreetMap y © Mapillary cuando se muestren fotos.

## 2. Pantallas

| Ruta | Pantalla | Contenido |
|---|---|---|
| `/onboarding` | Bienvenida (solo primer uso) | Explicación breve, permiso de ubicación, elegir plantilla de perfil |
| `/` | Mapa principal | Mapa, botón "¿A dónde vas?", botón capa de accesibilidad, botón centrar, indicador de perfil activo |
| `/search` | Búsqueda | Campo de texto, POIs, favoritos, recientes, "elegir en el mapa" |
| `/route` | Planificación | Origen/destino, resumen de hasta 2 rutas + comparación con la más corta, lista de avisos, botón "Iniciar" |
| `/route/segments` | Detalle de tramos | Lista accesible de segmentos con avisos |
| `/navigate` | Navegación | Instrucción actual grande, distancia, próximo aviso, recálculo automático |
| `/barrier/[id]` | Detalle de barrera | Tipo, foto, confianza, verificación, atribución |
| `/profiles` | Perfiles | Lista, activo, crear desde plantilla |
| `/profiles/[id]` | Editar perfil | Controles deslizantes con valores en texto (no solo color) y explicación de cada parámetro |
| `/settings` | Ajustes | Idioma, unidades, región, acerca de / licencias |

## 3. Estado
- `useProfileStore`: perfiles (`MobilityProfile` + `id`, `name`), `activeProfileId`. Persistido.
- `usePlacesStore`: favoritos y recientes (máx. 20). Persistido.
- `useRegionStore`: región actual (detectada por ubicación dentro de `boundary`, o elegida).
- `useSettingsStore`: idioma, unidades, región elegida, capa visible, bienvenida completada y **ubicación de demostración** (sitúa al usuario en el centro de la región activa y permite simular el recorrido; sirve para probar y para el E2E sin GPS). Persistido.
- `usePlanStore`: origen, destino, ruta seleccionada, ruta en navegación y posición actual. No persistido.
- Las rutas no se persisten; se cachean en React Query 5 min por clave (origen redondeado a 5 m, destino, hash de perfil).

## 4. Capa de accesibilidad
- Fuente vectorial `/tiles/edge_accessibility`: color por `status` **y** patrón de línea (continua = accesible, discontinua = precaución, punteada = no accesible, gris fino = sin datos) para no depender solo del color.
- Fuente `/tiles/barrier`: iconos por clase (escalera, bordillo, obstáculo, superficie), con borde distinto si está verificada.
- Leyenda accesible en hoja inferior.
- **Implementación actual de las barreras:** círculos con color por familia (escalera/escalón, bordillo, obstáculo, superficie u otra) y borde grueso si está verificada (`confirmed`/`manual`), fino si no. Los iconos por clase requieren un *sprite* propio en el estilo del mapa; queda pendiente hasta elegir el estilo base definitivo. La leyenda describe el mismo agrupamiento en texto.
- Las definiciones de capas viven en `mobile/src/features/map/layers.ts` y las comparten el renderizador nativo (`MapCanvas.tsx`, MapLibre Native) y el web (`MapCanvas.web.tsx`, MapLibre GL JS).

## 5. Accesibilidad de la propia app (obligatorio)
- Todos los controles con `accessibilityLabel`, `accessibilityRole`, `accessibilityHint` en español.
- Objetivos táctiles ≥ 48×48 dp; botones principales al alcance del pulgar (mitad inferior).
- Respetar tamaño de fuente del sistema (`allowFontScaling`) hasta 200 % sin cortar texto.
- Contraste ≥ 4,5:1; modo oscuro.
- La ruta y sus avisos deben ser comprensibles **sin ver el mapa**: la pantalla `/route/segments` es una lista lineal legible por lector de pantalla.
- Anunciar cambios importantes con `AccessibilityInfo.announceForAccessibility` (ruta calculada, recálculo, aviso próximo).
- Probar con TalkBack y VoiceOver antes de cerrar cada pantalla.
- Las pendientes llevan signo según el sentido de la marcha; la app nunca muestra el signo: dice "X % de subida" o "X % de bajada".

### 5.1 Lista de comprobación manual (TalkBack / VoiceOver)
Las pruebas automáticas (`mobile/__tests__/screens.test.tsx`) recorren el árbol de accesibilidad, pero no sustituyen a un lector de pantalla real. Antes de publicar un build:
1. Bienvenida: se leen el título, la explicación y cada plantilla como opción única con su resumen; "Empezar" anuncia que está desactivado hasta elegir.
2. Mapa: los botones "¿A dónde vas?", capa, centrar y leyenda están en la mitad inferior y se leen con su estado; la leyenda se cierra con el gesto de atrás.
3. Búsqueda: cada lugar se lee como "nombre. categoría · entrada"; la estrella de favorito es un botón aparte con el nombre del lugar.
4. Planificación: al terminar el cálculo se anuncia el resumen; cada ruta es una opción con distancia, duración, puntuación, pendiente y estado; se lee por qué no se usa la ruta más corta y cada barrera abre su detalle.
5. Tramos: la lista se entiende de principio a fin sin mirar el mapa (estado, distancia, pendiente, superficie y avisos en una sola frase por tramo).
6. Navegación: la instrucción actual se vuelve a leer al cambiar; se anuncian aviso próximo, desvío, recálculo y llegada.
7. Perfil: cada límite se puede cambiar con los botones − y + además del deslizador, y el valor se lee tras cada cambio.
8. Tamaño de fuente del sistema al 200 % y modo oscuro: ningún texto se corta y los botones siguen midiendo ≥ 48 dp.

## 6. Configuración
Plantilla en `mobile/.env.example`. `EXPO_PUBLIC_API_URL`, `EXPO_PUBLIC_TILES_URL`, `EXPO_PUBLIC_MAP_STYLE_URL`, `EXPO_PUBLIC_SENTRY_DSN` (opcional). Perfiles `development`, `preview`, `production` en `eas.json`.

El plugin Expo `mobile/plugins/with-windows-cmake-paths.js` configura
`android.cmakeVersion=3.31.6` para todos los módulos Android. Su Ninja admite las rutas largas
de los objetos nativos en Windows. Se aplica durante `expo prebuild` y conserva las rutas
originales de las fuentes. Instrucciones para compilar e instalar por USB en `mobile/README.md`.
También establece `expo.android.cmakeObjectPathMax=240` y admite `REDUC_NATIVE_BUILD_ROOT`
como carpeta temporal corta para los objetos de la app cuando Windows no permite rutas largas.
El empaquetado JavaScript declara los archivos `mobile/.env*` y las variables `EXPO_PUBLIC_*`
como entradas de Gradle para regenerar el APK cuando cambien las URLs de sus servicios.

## 7. Panel de administración (admin/)
React + Vite + MapLibre GL JS. Vistas: Login; Regiones (dibujar/subir polígono, config JSON con validación); Ejecuciones del pipeline (progreso por etapa, logs, relanzar etapa); **Cola de verificación** (mapa + recorte de foto + atajos de teclado: `A` confirmar, `R` rechazar, `E` editar, `→` siguiente); Subida de fotos (arrastrar, previsualizar GPS y rumbo); Versiones del mapa (diferencias con la publicada, botón publicar); Métricas.
