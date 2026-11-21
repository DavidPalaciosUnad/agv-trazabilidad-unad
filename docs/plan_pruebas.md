# Plan y resultados de pruebas

Niveles de prueba (ISO/IEC/IEEE 29119 como referencia): unitarias, de integración, de sistema en el gemelo digital y ensayos de verificación por simulación. Todas las pruebas son reproducibles con los comandos del README; los ensayos usan semillas fijas.

## Resumen de ejecución

| Nivel | Herramienta | Casos | Resultado |
|---|---|---|---|
| Unitarias del núcleo del firmware (C++) | `make -C firmware/test` | 29 | 29 superadas |
| Compilación sintáctica del sketch (núcleos ESP32 2.x y 3.x) | g++ con encabezados de reemplazo | 2 | Correcta |
| Unitarias y de integración del módulo de gestión | `pytest` | 38 | 38 superadas |
| Integración extremo a extremo por MQTT (broker local + AGV emulado) | `pytest tests/test_mqtt_integracion.py` | 1 (incluida en las 38) | Superada |
| Sintonía y robustez del seguimiento de línea | `simulacion/seguimiento_linea.py` | 396 combinaciones + 6 escenarios + 30 semillas | 0 pérdidas de línea |
| Campos de advertencia y protección | `simulacion/frenado_obstaculo.py` | 1 estático + 240 intrusiones | 0 contactos; holgura mínima 0,16 m |
| Jornada simulada en el gemelo digital | `simulacion/gemelo_lote.py` | 40 órdenes, 6 intrusiones, 1 emergencia | 40/40 completadas; cadena íntegra |

## Resultados clave

**Seguimiento de línea (RNF-02).** Ganancias seleccionadas: Kp = 2,0; Kd = 0,08; Ki = 0 (error normalizado ±1 = ±40 mm). A 0,5 m/s: error RMS 0,95 mm y máximo 2,41 mm; a 0,2 m/s: RMS 3,27 mm y máximo 7,84 mm; con arranque desviado 20 mm y 5°, convergencia sin pérdida de línea. En 30 semillas de ruido: RMS medio 0,94 mm y peor máximo 3,03 mm, frente al límite de diseño de 25 mm.

**Detección de obstáculos (RS-01, RS-02).** Distancia de parada teórica a 0,5 m/s: 0,175 m. Obstáculo estático: el AGV reduce a 0,20 m/s en el campo de advertencia y se detiene con 0,46 m de holgura. Intrusiones súbitas entre 0,3 m y 1,5 m (30 ensayos por distancia): 240 detenciones, 0 contactos, holgura mínima de 0,16 m (intrusión a 0,3 m, dentro del campo de protección).

**Jornada simulada (sistema integrado).** 40 órdenes completadas (tasa de éxito 100 %), 1 011,9 kg transportados, 684 m recorridos, tiempo medio de ciclo 51,1 s y de ejecución 43,9 s; 6 intrusiones simuladas (3 entraron al campo de advertencia y 2 de ellas exigieron parada), 1 parada de emergencia con rearme manual, 651 eventos encadenados íntegros. Al alterar un registro intermedio, la verificación falla exactamente en el evento siguiente al alterado.

## Defecto detectado y corregido durante la verificación

El primer ensayo de intrusión súbita mostró holguras irreales (el AGV parecía detenerse en 2 cm desde 0,5 m/s). La causa era que el modelo dejaba de integrar el desplazamiento al pasar al estado DETENIDO_OBSTACULO, aunque el vehículo seguía frenando. Se corrigió en el firmware y en el gemelo digital (el desplazamiento se integra mientras la velocidad sea positiva) y se agregó la desaceleración de emergencia de 2 m/s². Tras la corrección, las holguras coinciden con la distancia de parada teórica.

## Pendiente para el montaje físico (fases siguientes)

Compilación con el núcleo real y ejecución en Wokwi (captura del grupo), calibración del arreglo de línea, medición real de la distancia de frenado con carga nominal, ensayo de la seta con relé de seguridad y pruebas de autonomía de la batería.
