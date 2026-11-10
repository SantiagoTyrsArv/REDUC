# 01 — PRD: Requisitos del producto

## 1. Visión

Que una persona en silla de ruedas pueda moverse por el campus (y luego por cualquier ciudad) con una ruta en la que **confía**: sin escalones inesperados, sin bordillos sin rampa, sin pendientes que superen su capacidad y sin superficies impracticables.

**Diferenciador:** el mapa de accesibilidad no depende de reportes ciudadanos. Se genera automáticamente analizando imágenes de nivel de calle con visión por computadora, y en el piloto se verifica con fotografías propias.

## 2. Usuarios

| Rol | Descripción | Necesidad principal |
|-----|-------------|---------------------|
| **Usuario final** | Persona en silla manual, eléctrica o scooter; también acompañantes | Ruta accesible según su perfil, con avisos claros |
| **Verificador** | Miembro del equipo del proyecto en el piloto | Revisar detecciones automáticas, corregir, subir fotos propias |
| **Administrador** | Responsable técnico | Dar de alta regiones, lanzar procesamientos, ver métricas |

## 3. Casos de uso principales

- **CU-01 Calcular ruta accesible.** El usuario elige origen (ubicación actual o punto en el mapa/buscador) y destino; recibe la ruta más accesible para su perfil, con distancia, tiempo estimado, puntuación de accesibilidad y avisos por tramo.
- **CU-02 Comparar con la ruta más corta.** La app muestra cuánto más larga es la ruta accesible y por qué evita la corta (p. ej. "la ruta corta tiene 3 escalones").
- **CU-03 Configurar perfil de movilidad.** Tipo de silla, pendiente máxima de subida/bajada, altura máxima de desnivel, ancho mínimo, tolerancia a superficies, evitar tramos no verificados.
- **CU-04 Ver el mapa de accesibilidad.** Capa sobre el mapa con tramos coloreados (accesible / con precaución / no accesible / sin datos) y puntos de barrera (escalón, falta de rampa, obstáculo, superficie dañada).
- **CU-05 Ver detalle de una barrera.** Tipo, confianza, fuente, foto recortada, estado de verificación.
- **CU-06 Navegación paso a paso (básica).** Seguir la ruta con la posición GPS e instrucciones de giro; recalcular si el usuario se desvía.
- **CU-07 Ingerir imágenes de una región** (admin). Desde Mapillary por polígono, desde Street View (si se habilita) o subiendo fotos propias con GPS.
- **CU-08 Verificar detecciones** (verificador). Aceptar, rechazar, corregir tipo/posición/atributos; añadir barreras manuales desde foto propia.
- **CU-09 Dar de alta una región nueva** (admin). Polígono + fuentes de imágenes → importar red peatonal OSM → procesar imágenes → generar mapa → publicar.

## 4. Requisitos funcionales

### App móvil (usuario final)
- **RF-01** Mapa base con la posición del usuario y la región activa.
- **RF-02** Búsqueda de lugares dentro de la región (POIs del campus: edificios, entradas accesibles, baños accesibles, parqueaderos) y selección por toque en el mapa.
- **RF-03** Cálculo de ruta accesible según el perfil activo; mostrar hasta 2 alternativas.
- **RF-04** Resumen de ruta: distancia, tiempo estimado (según velocidad del perfil), puntuación de accesibilidad 0–100, número de tramos con precaución, porcentaje de tramos verificados.
- **RF-05** Lista de avisos por tramo (pendiente X %, superficie irregular, cruce sin rampa evitado, etc.).
- **RF-06** Si no existe ruta que cumpla las restricciones duras, informar el motivo y ofrecer la "menos mala" marcando las barreras que contiene.
- **RF-07** Gestión de perfiles de movilidad: crear, editar, elegir activo. Plantillas predefinidas (manual, manual con asistente, eléctrica, scooter).
- **RF-08** Capa de accesibilidad activable con leyenda.
- **RF-09** Detalle de barrera con foto (si la licencia lo permite) y estado de verificación.
- **RF-10** Navegación paso a paso con recálculo ante desvío > 25 m.
- **RF-11** Favoritos (lugares guardados) y últimas rutas, almacenados localmente.
- **RF-12** Uso sin cuenta (anónimo). Los perfiles viven en el dispositivo y se envían en cada solicitud de ruta.
- **RF-13** Interfaz en español (i18n preparado para inglés).

### Backend y pipeline
- **RF-20** Modelo multirregión: toda entidad geográfica pertenece a una región.
- **RF-21** Importar la red peatonal desde OpenStreetMap para el polígono de la región (aceras, senderos, cruces, escaleras, rampas, ascensores).
- **RF-22** Enriquecer el grafo con elevación (MDE) para calcular pendientes por tramo.
- **RF-23** Ingerir imágenes de calle mediante proveedores intercambiables (`mapillary`, `upload`, `streetview` opcional).
- **RF-24** Detectar automáticamente: escalones/escaleras, bordillo sin rampa, rampa presente, obstáculo en acera, superficie en mal estado, pendiente pronunciada (indicador visual), ausencia de acera.
- **RF-25** Geolocalizar cada detección y asociarla al tramo o nodo del grafo correspondiente.
- **RF-26** Fusionar detecciones múltiples (varias imágenes de la misma barrera) en una sola barrera con confianza agregada.
- **RF-27** Calcular atributos de accesibilidad por tramo a partir de OSM + MDE + barreras.
- **RF-28** Servir rutas con función de costo parametrizada por perfil.
- **RF-29** Servir la capa de accesibilidad como teselas vectoriales.
- **RF-30** Panel web de verificación con cola de detecciones ordenadas por incertidumbre.
- **RF-31** Versionado del mapa: cada procesamiento genera una versión; solo la versión publicada se usa para rutas.
- **RF-32** Desenfoque automático de rostros y matrículas en fotos propias antes de almacenarlas.

## 5. Requisitos no funcionales

| ID | Requisito | Meta |
|----|-----------|------|
| RNF-01 | Latencia de cálculo de ruta en el campus | p95 < 800 ms |
| RNF-02 | Latencia de teselas | p95 < 300 ms |
| RNF-03 | Precisión del detector (clases críticas: escalón, bordillo sin rampa) | Recall ≥ 0,85, precisión ≥ 0,75 en el conjunto de validación del campus |
| RNF-04 | Error de geolocalización de barreras | Mediana < 5 m |
| RNF-05 | Seguridad: nunca recomendar como "accesible" un tramo con barrera crítica confirmada | 0 casos en pruebas de regresión |
| RNF-06 | Accesibilidad de la app | WCAG 2.2 AA; compatible con TalkBack y VoiceOver; objetivos táctiles ≥ 48 dp |
| RNF-07 | Plataformas | Android 10+ e iOS 16+ |
| RNF-08 | Privacidad | Sin cuenta obligatoria; ubicación no se almacena en servidor; logs sin coordenadas exactas |
| RNF-09 | Extensibilidad | Nueva región = configuración + ejecución del pipeline, sin cambios de código |
| RNF-10 | Licencias | Respetar licencias de cada fuente (CC BY-SA de Mapillary, ODbL de OSM, ToS de Google) |
| RNF-11 | Cobertura de pruebas | Backend ≥ 80 % en módulos de dominio (ruteo, fusión, costo) |

## 6. Alcance

### MVP (piloto campus)
RF-01 a RF-09, RF-11 a RF-13, RF-20 a RF-31 (con Street View desactivado), panel de verificación básico.

### Fase 2
RF-10 navegación paso a paso completa con voz, RF-32 automático, modo sin conexión (descarga del grafo de la región), interiores (ascensores, edificios), segunda región (ciudad).

### Fuera de alcance
Reportes ciudadanos como fuente principal (se puede añadir luego como fuente más), transporte público, cuentas sociales.

## 7. Métricas de éxito del piloto
- ≥ 90 % de los tramos peatonales del campus con datos de accesibilidad.
- ≥ 70 % de las barreras críticas verificadas por el equipo.
- En pruebas con usuarios: ≥ 80 % de las rutas calificadas como "realizables sin ayuda" por personas usuarias de silla de ruedas.
- 0 rutas recomendadas que atraviesen una barrera crítica confirmada.
