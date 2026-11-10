# 10 — Decisiones (ADR), riesgos y preguntas abiertas

## Decisiones de arquitectura

**ADR-001 App multiplataforma con Expo/React Native.** Un solo código para Android e iOS, buen soporte de accesibilidad nativa y de MapLibre. Alternativa descartada: Flutter (menos afinidad con el panel web en React y el cliente TS generado).

**ADR-002 Backend en Python/FastAPI.** El pipeline de visión es Python (PyTorch); compartir `core/` entre API y worker evita duplicar dominio. Alternativa: Node/NestJS (obligaría a dos lenguajes en el backend).

**ADR-003 PostGIS + pgRouting.** Permite costos por perfil calculados en SQL en cada consulta, sin reconstruir el grafo. Suficiente para un campus y una ciudad mediana con subgrafo por bbox.

**ADR-004 Motor de rutas detrás de `RoutingEngine`.** Si una región grande no cumple el p95, se implementa otro motor (GraphHopper custom models / Valhalla) consumiendo `edge_accessibility`, sin cambiar API ni app.

**ADR-005 Observación ≠ barrera.** Las detecciones nunca afectan el ruteo directamente; pasan por fusión y verificación. Permite auditar, reentrenar y transferir verificaciones entre versiones.

**ADR-006 Street View desactivado por defecto.** Los Términos de Google Maps Platform restringen almacenar imágenes y crear bases de datos derivadas de su contenido. Fuente principal: Mapillary (CC BY-SA 4.0) + fotos propias. Activar Street View solo con autorización legal explícita.

**ADR-007 Uso anónimo.** Los perfiles de movilidad son datos sensibles de salud; se quedan en el dispositivo y viajan solo en la solicitud de ruta, sin registrarse.

**ADR-008 Mapa versionado.** Publicación explícita para que un procesamiento a medias o un modelo peor nunca afecte a usuarios.

**ADR-009 Renderizado y concurrencia en clientes.** El panel administrativo mantiene CSR con React/Vite: es una aplicación privada, sin necesidad de SEO ni de SSR/SSG; la app de usuario es nativa con Expo. Desde T-32 se medirá INP y se evitarán tareas largas y cadenas de microtareas que bloqueen interacciones. Un Web Worker y `postMessage` solo se introducirán si una medición demuestra que procesamiento de geometrías o imágenes bloquea el hilo principal; el worker Python existente ya ejecuta la visión pesada en el servidor. `SharedArrayBuffer` y `crossOriginIsolated` no se habilitan sin ese caso justificado, porque exigen COOP/COEP y una auditoría de todos los recursos de origen cruzado. El progreso del pipeline usará inicialmente consultas REST con TanStack Query; WebSockets solo se añadirá si el polling no cumple una necesidad medida de actualización en tiempo real.

## Riesgos

| Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|
| Poca cobertura de Mapillary en el campus | Alta | Alto | Campaña propia de fotos (app Mapillary o cámara 360°) y subida por `upload`; coverage visible en la capa |
| Pendientes imprecisas con MDE de baja resolución | Alta | Alto | MDE de dron/LiDAR o mediciones con inclinómetro en tramos críticos; penalizar incertidumbre |
| Falsos negativos en escalones/bordillos (peligroso) | Media | Muy alto | Umbral bajo de detección, penalización por incertidumbre, verificación humana obligatoria de barreras críticas antes de publicar en el piloto |
| Error de geolocalización asigna barrera al tramo equivocado | Media | Alto | Asociación con restricción de rumbo, revisión de barreras sin tramo, pruebas de error en campo |
| Licencias de datos/modelos (Ultralytics AGPL, imágenes de Project Sidewalk) | Media | Medio | Preferir RT-DETR (Apache-2.0); revisar licencias antes de uso comercial |
| Datos insuficientes para entrenar | Media | Alto | Empezar con modelos preentrenados (Vistas) + Project Sidewalk; anotar ~1 500 imágenes del campus |
| Dependencia de servicios externos (Overpass, Mapillary) | Media | Bajo | Caché de descargas, soporte de archivos .pbf locales |

## Preguntas abiertas (valores por defecto asumidos)

1. **Campus piloto:** nombre/ubicación y polígono. *Por defecto:* se carga como región configurable; el agente usa la región sintética hasta tenerlo.
2. **Plataforma:** ¿Android e iOS o solo Android? *Por defecto:* ambas vía Expo; si solo hay un dispositivo de prueba, priorizar Android.
3. **Hardware:** ¿hay GPU para entrenar? *Por defecto:* entrenamiento en Google Colab/Kaggle; inferencia en CPU.
4. **Datos anotados:** ¿quién anota las fotos del campus? *Por defecto:* el equipo con Label Studio, siguiendo `ml/datasets/README.md`.
5. **Elevación:** ¿existe un MDE/LiDAR del campus? *Por defecto:* Copernicus GLO-30 + mediciones manuales en tramos críticos.
6. **Plazo y tamaño del equipo:** afecta si se hace la navegación paso a paso en el MVP. *Por defecto:* fuera del MVP (fase 2) salvo la versión básica.
7. **Repositorio:** dónde vivirá el código. *Por defecto:* monorepo nuevo en GitHub `app-reduc`.
