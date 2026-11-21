# Arquitectura

## Capas

1. **Física**: ESP32-DevKitC V4; HC-SR04 frontal (TRIG GPIO5, ECHO GPIO18 con divisor 5 V→3,3 V); arreglo de línea (ADC GPIO34); seta de emergencia NC (GPIO27, además corta la potencia de los motores por relé de seguridad en el montaje físico); pulsador de rearme (GPIO26); LED verde/ámbar/rojo (GPIO25/33/32); zumbador (GPIO19); PWM de motores (GPIO16/17); LCD 20×4 I2C (SDA 21, SCL 22).
2. **Control** (`agv_core`): máquina de estados `REPOSO → EN_RUTA ⇄ EN_ESTACION`, `EN_RUTA ⇄ DETENIDO_OBSTACULO`, cualquier estado → `PARADA_EMERGENCIA` → (rearme) estado previo; PID de seguimiento de línea; perfiles de aceleración y frenado; vigilancia de comunicación.
3. **Gestión** (`gestion/`): Flask + SQLite; despacho por prioridad; Dijkstra; bitácora encadenada SHA-256; indicadores; NIOSH; gemelo digital a 20 Hz.

## Protocolo MQTT

| Tópico | Sentido | Contenido |
|---|---|---|
| `<prefijo>/<agv>/cmd` | gestión → AGV | `ORD|id|nodo0|n1:d1;n2:d2|k_carga|k_descarga`, `CAN|id`, `PING|t`, `EST|1`, `RST|1` |
| `<prefijo>/<agv>/telemetria` | AGV → gestión (1 Hz) | `{"agv","st","zona","ord","nodo","sig","s","v","d","bat"}` |
| `<prefijo>/<agv>/evento` | AGV → gestión | `{"ev","orden","nodo","agv"}` |

## Modelo de datos

`ordenes(id, codigo, origen, destino, masa_kg, descripcion, solicitante, prioridad, estado, agv_id, distancia_m, creada, asignada, iniciada, completada)`
`eventos(id, ts, tipo, orden_id, agv_id, detalle, hash_prev, hash)`
`telemetria(id, ts, agv_id, estado, zona, nodo, x, y, v, d_obst, bateria)`
`evaluaciones_niosh(id, ts, tarea, momento, L, H, V, D, A, F, duracion_h, agarre, RWL, LI)`
