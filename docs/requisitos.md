# Especificación de requisitos

Valores de diseño definidos en la etapa *Diseñar* (CDIO) y en el Sprint 0. La columna «Verificación» remite a la prueba automatizada o al ensayo que demuestra el cumplimiento.

## Requisitos funcionales

| ID | Requisito | Verificación |
|---|---|---|
| RF-01 | Registrar órdenes de transporte con origen, destino, masa, prioridad, código del solicitante y descripción. | `tests/test_api.py::test_crear_despachar_y_completar_orden` |
| RF-02 | Validar masa (0 < m ≤ 50 kg), estaciones existentes, origen ≠ destino y código de rol. | `test_validacion_de_entradas` (6 casos) |
| RF-03 | Asignar automáticamente las órdenes pendientes al AGV disponible por prioridad y antigüedad. | `test_prioridad_en_el_despacho` |
| RF-04 | Calcular la ruta más corta sobre la guía (Dijkstra) con paradas de carga y descarga. | `test_ruta_mas_corta_dijkstra`, `test_plan_orden_indices_de_carga_y_descarga` |
| RF-05 | Ejecutar la ruta con permanencia en las estaciones de carga y descarga y atravesar los nodos de paso sin detenerse. | `test_ciclo_completo_con_eventos`, `test_nodo_de_paso_sin_detenerse`, `test_core.cpp` §2 |
| RF-06 | Registrar cada evento de la orden y del AGV con marca de tiempo en una bitácora encadenada SHA-256. | `test_trazabilidad.py`, `gemelo_lote.py` |
| RF-07 | Verificar la integridad de la bitácora y detectar alteraciones o eliminaciones. | `test_detecta_alteracion_de_detalle`, `test_detecta_eliminacion_de_registro` |
| RF-08 | Mostrar estado, zona de detección, posición y batería del AGV en el gemelo digital en tiempo real. | Inspección de la interfaz (captura de pantalla) |
| RF-09 | Rechazar órdenes cuando la batería sea inferior al 15 % o el AGV esté ocupado. | `test_rechazos_bateria_y_ocupado`, `test_core.cpp` §5 |
| RF-10 | Calcular indicadores: traslados manuales evitados, masa transportada, tiempos de ciclo, tasa de éxito y paradas. | `test_crear_despachar_y_completar_orden`, `gemelo_lote.py` |
| RF-11 | Exportar órdenes, eventos, telemetría y evaluaciones NIOSH en CSV. | `test_niosh_y_exportacion` |
| RF-12 | Calcular RWL y LI (NIOSH) y registrar evaluaciones de línea base y posintervención. | `test_niosh.py` (5 pruebas) |
| RF-13 | Cancelar órdenes no cerradas y detener el AGV. | `test_cancelacion` |

## Requisitos no funcionales

| ID | Requisito | Verificación |
|---|---|---|
| RNF-01 | Velocidad nominal 0,50 m/s y reducida 0,20 m/s. | `test_core.cpp` §2–§3 |
| RNF-02 | Desviación lateral ≤ 25 mm en recta y curva de radio 1 m. | `simulacion/seguimiento_linea.py` |
| RNF-03 | Lazo de control a 50 Hz; telemetría a 1 Hz; sensor ultrasónico cada 60 ms. | Revisión de código (`sketch.ino`) |
| RNF-04 | Comunicación MQTT con QoS 1 para comandos y eventos. | `tests/test_mqtt_integracion.py` |
| RNF-05 | Núcleo de control portable, probado en PC y compartido con el gemelo digital. | `make -C firmware/test` |
| RNF-06 | Seguridad de la información: validación de entradas, consultas parametrizadas, clave de API para escritura, cabeceras HTTP de seguridad y minimización de datos personales. | `test_validacion_de_entradas`, `test_clave_api_obligatoria_si_esta_configurada` |
| RNF-07 | Portabilidad: Python 3.10+ en Windows, Linux o macOS; firmware compatible con núcleos ESP32 2.x y 3.x. | Integración continua; `make compilar_sketch` |

## Requisitos de seguridad funcional (referencia ISO 3691-4, ISO 12100, ISO 13849-1)

| ID | Requisito | Verificación |
|---|---|---|
| RS-01 | Campo de advertencia de 1,20 m: reducción a velocidad reducida. | `test_zonas_y_parada_por_obstaculo`, `frenado_obstaculo.py` |
| RS-02 | Campo de protección de 0,50 m: parada sin contacto y con holgura ≥ 0,15 m. | `frenado_obstaculo.py` (240 ensayos) |
| RS-03 | Reanudación automática solo tras 2 s continuos de campo despejado. | `test_core.cpp` §3 |
| RS-04 | Parada de emergencia enclavada; rearme manual explícito con la seta liberada. | `test_emergencia_requiere_rearme_manual`, `test_core.cpp` §4 |
| RS-05 | Pérdida de comunicación > 10 s: modo seguro a velocidad reducida. | `test_watchdog_de_comunicacion`, `test_core.cpp` §6 |
| RS-06 | Señalización luminosa (verde, ámbar, rojo) y acústica del estado. | Revisión de código y simulación en Wokwi |
