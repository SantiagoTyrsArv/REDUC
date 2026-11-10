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

### Android físico en Windows

Configura `JAVA_HOME` con un JDK compatible con Gradle y `ANDROID_HOME` con el SDK de Android.
Para este proyecto se verificó JDK 25 con Gradle 9.4.1. Conecta el teléfono por USB, activa la
depuración USB y acepta su autorización; `adb devices` debe mostrar el estado `device`.
En `mobile/.env.local`, usa la IP LAN del equipo para la API (`:8000`) y las teselas (`:3000`);
el móvil debe poder acceder a esa red y los servicios de Docker deben estar activos.

Para una conexión estable por USB, también puedes usar `http://127.0.0.1:8000` y
`http://127.0.0.1:3000` en esas variables, y ejecutar antes de abrir la app:

```powershell
adb reverse tcp:8000 tcp:8000
adb reverse tcp:3000 tcp:3000
```

Esta configuración necesita el cable conectado y repetir los reenvíos tras reconectar el móvil.
Los valores `EXPO_PUBLIC_*` se incluyen en el APK: recompila cuando cambies sus URLs.
El plugin registra los archivos `.env*` y las variables `EXPO_PUBLIC_*` como entradas del
empaquetado JavaScript para que Gradle invalide su caché cuando cambien.

```powershell
pnpm --filter @reduc/mobile exec expo prebuild --platform android --no-install
pnpm --filter @reduc/mobile android
```

El plugin `plugins/with-windows-cmake-paths.js` selecciona CMake 3.31.6 para todos los módulos
Android. Su Ninja admite las rutas largas que genera React Native en Windows y evita los errores
`ninja: error: mkdir(...)` / `Filename longer than 260 characters`, conservando las rutas del código
fuente y sin modificar `node_modules`. Se conserva al regenerar Android. Instala esa versión desde
SDK Manager si no está disponible; Gradle también puede descargarla con las licencias aceptadas.

Si Windows tiene desactivado `LongPathsEnabled`, el plugin también limita los objetos a 240
caracteres. En una ruta de repositorio larga, el módulo principal necesita además una carpeta
temporal corta. Desde la raíz, asigna una unidad libre (por ejemplo, `R:`):

```powershell
$repoRoot = (Get-Location).Path
subst R: $repoRoot
```

Añade `REDUC_NATIVE_BUILD_ROOT=R:/.cxx` a `mobile/.env.local` y ejecuta de nuevo `expo prebuild`
antes de compilar. Mantén la unidad asignada durante la compilación; tras reiniciar Windows,
repite `subst`. Solo los objetos CMake de la app usan esa ruta: Gradle y la generación de código
siguen usando la ruta original del repositorio para evitar errores entre raíces `C:` y `R:`.

Para generar un APK local con JavaScript incluido (sin Metro), desde la raíz del repositorio:

```powershell
$env:NODE_ENV = 'production'
./mobile/android/gradlew.bat -p mobile/android :app:assembleRelease -PreactNativeArchitectures=arm64-v8a
adb install -r mobile/android/app/build/outputs/apk/release/app-release.apk
adb shell am start -n app.reduc.mobile/.MainActivity
```

`arm64-v8a` corresponde al teléfono probado; consulta `adb shell getprop ro.product.cpu.abi`
para otros dispositivos. Este APK local usa la firma de desarrollo del proyecto generado;
la distribución de producción requiere su propia firma.

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
