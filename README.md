# AGV de bajo costo con trazabilidad de órdenes de transporte

Prototipo funcional (nivel de madurez tecnológica **TRL 5 en entorno relevante simulado**) del proyecto de grado
*«Prototipo de vehículo autónomo guiado (AGV) de bajo costo para la reducción del riesgo biomecánico por
manipulación manual de cargas en microempresas manufactureras»* — Ingeniería de Sistemas, ECBTI, UNAD.

El sistema tiene tres capas:

| Capa | Componente | Carpeta |
|---|---|---|
| Física | ESP32-DevKitC V4, sensor ultrasónico HC-SR04, arreglo de línea, seta de emergencia, LCD 20×4, drivers de motor (simulados en Wokwi) | `firmware/agv_esp32/` |
| Control | Máquina de estados, seguimiento de línea PID, campos de advertencia y protección, vigilancia de comunicación | `firmware/agv_esp32/agv_core.*` |
| Gestión | API REST + interfaz web, despacho de órdenes, ruta más corta (Dijkstra), bitácora encadenada SHA-256, indicadores, calculadora NIOSH, gemelo digital de la planta | `gestion/` |

## Ejecución rápida (gemelo digital)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    ·    Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python -m gestion.app
```

Abrir <http://127.0.0.1:5000>. Registrar una orden (p. ej. Bodega → Estación 2, 20 kg), observar el AGV en el mapa,
simular un obstáculo, accionar la parada de emergencia y el rearme, y consultar la bitácora de trazabilidad.

Variables de entorno opcionales:

| Variable | Valor por defecto | Uso |
|---|---|---|
| `AGV_MODO` | `simulado` | `mqtt` para conectar con el ESP32 (Wokwi o físico) |
| `AGV_FACTOR_TIEMPO` | `1.0` | Acelera el gemelo digital (p. ej. `5`) |
| `AGV_API_KEY` | vacío | Si se define, las operaciones de escritura exigen la cabecera `X-API-Key` |
| `AGV_MQTT_HOST` / `AGV_MQTT_PORT` | `broker.hivemq.com` / `1883` | Broker MQTT |
| `AGV_MQTT_PREFIJO` | `unad/agv-pg` | Prefijo de tópicos (debe coincidir con el firmware) |
| `AGV_DB` | `agv_gestion.db` | Base de datos SQLite |

## Firmware en Wokwi

1. Crear un proyecto ESP32 en <https://wokwi.com> y reemplazar `sketch.ino` y `diagram.json` por los de `firmware/agv_esp32/`.
2. Agregar los archivos `agv_core.h`, `agv_core.cpp` y `libraries.txt` (botón «+» del editor).
3. Ejecutar la simulación. Para enlazarla con el módulo de gestión: `AGV_MODO=mqtt python -m gestion.app` (cambiar `AGV_MQTT_PREFIJO` y `PREFIJO` por un valor propio del grupo para no compartir tópicos en el broker público).
4. Controles: control deslizante del HC-SR04 = distancia a una persona u obstáculo; potenciómetro = desviación de la cinta; botón rojo = parada de emergencia; botón verde = rearme.

## Pruebas y ensayos

```bash
python -m pytest -v                    # módulo de gestión, gemelo digital, NIOSH, trazabilidad, MQTT extremo a extremo
make -C firmware/test                  # núcleo del firmware en C++ y compilación sintáctica del sketch
python simulacion/seguimiento_linea.py # sintonía del PID y desviación lateral
python simulacion/frenado_obstaculo.py # campos de advertencia/protección (240 ensayos de intrusión)
python simulacion/gemelo_lote.py       # jornada simulada de 40 órdenes con intrusiones y emergencia
```

Los resultados de los ensayos quedan en `simulacion/resultados/` (JSON y figuras).

## Estructura

```
firmware/agv_esp32/   sketch.ino, agv_core.h/.cpp, diagram.json, libraries.txt
firmware/test/        pruebas unitarias del núcleo (g++) y encabezados de reemplazo
gestion/              app.py (API/interfaz), servicio.py, agv.py, planta.py, protocolo.py,
                      trazabilidad.py, niosh.py, db.py, mqtt_puente.py, static/
simulacion/           ensayos de verificación y resultados
tests/                pruebas automatizadas (pytest)
docs/                 requisitos, arquitectura, plan y resultados de pruebas, manual de operación
```

## Publicación del repositorio y acceso del tutor

- **Repositorio público** (recomendado): cualquier persona con el enlace tiene acceso de lectura.
- **Repositorio privado con rol de lectura**: en una cuenta personal los colaboradores reciben permiso de escritura;
  para otorgar exactamente el rol *Read* se crea una organización gratuita, se transfiere el repositorio y se invita
  al tutor con ese rol (*Settings → Collaborators and teams → Add people → Read*).

## Licencia

MIT. Datos personales: el sistema registra solo códigos de rol (p. ej. `OP-01`), nunca nombres, conforme a la Ley 1581 de 2012.
