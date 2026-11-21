"""Parámetros de diseño del sistema AGV y del módulo de gestión.

Todos los valores de este archivo son PARÁMETROS DE DISEÑO (requisitos
especificados por el equipo en la etapa Diseñar), no mediciones de campo.
El layout de la planta es un layout de referencia parametrizable: debe
reemplazarse por el levantamiento real de la microempresa (Fase 1 del
cronograma) editando la sección PLANTA.
"""
from dataclasses import dataclass, field
import os


@dataclass(frozen=True)
class ParametrosAGV:
    # Cinemática y desempeño (RNF-01, RNF-02)
    v_nominal: float = 0.50          # m/s, velocidad máxima en campo libre
    v_reducida: float = 0.20         # m/s, velocidad en campo de advertencia
    a_aceleracion: float = 0.50      # m/s^2
    a_frenado: float = 1.00          # m/s^2, desaceleración de frenado de servicio
    a_emergencia: float = 2.00       # m/s^2, parada de emergencia (corte de potencia + freno)
    carga_nominal_kg: float = 50.0   # kg (RF-02)
    # Campos de detección (RS-01, RS-02) inspirados en ISO 3691-4
    d_advertencia: float = 1.20      # m, campo de advertencia -> velocidad reducida
    d_proteccion: float = 0.50       # m, campo de protección -> parada
    t_reanudar: float = 2.0          # s de campo despejado antes de reanudar (RS-03)
    t_reaccion: float = 0.10         # s, latencia sensor + lazo de control
    # Operación
    t_estacion: float = 4.0          # s de permanencia para carga/descarga
    bateria_min_orden: float = 15.0  # %, por debajo se rechazan órdenes (RF-09)
    consumo_por_metro: float = 0.05  # %/m (modelo simplificado de descarga)
    consumo_reposo: float = 0.001    # %/s
    t_watchdog_com: float = 10.0     # s sin latido del servidor -> modo seguro (RS-05)


PARAM = ParametrosAGV()

# ---------------------------------------------------------------------------
# PLANTA: layout de referencia de una microempresa manufacturera.
# Coordenadas en metros. Las aristas siguen la guía (cinta) del piso.
# ---------------------------------------------------------------------------
ESTACIONES = {
    "H":  {"nombre": "Base de carga del AGV", "x": 1.0,  "y": 1.0, "tipo": "base"},
    "B":  {"nombre": "Bodega de materia prima", "x": 1.0, "y": 7.0, "tipo": "bodega"},
    "E1": {"nombre": "Estación 1 - Corte",     "x": 7.0,  "y": 7.0, "tipo": "proceso"},
    "E2": {"nombre": "Estación 2 - Ensamble",  "x": 13.0, "y": 7.0, "tipo": "proceso"},
    "E3": {"nombre": "Estación 3 - Acabado",   "x": 13.0, "y": 1.0, "tipo": "proceso"},
    "D":  {"nombre": "Zona de despacho",       "x": 7.0,  "y": 1.0, "tipo": "despacho"},
}

# Aristas bidireccionales de la guía (longitud calculada por geometría)
ARISTAS = [("H", "B"), ("B", "E1"), ("E1", "E2"), ("E2", "E3"),
           ("E3", "D"), ("D", "H"), ("E1", "D")]

AGVS_INICIALES = [{"id": "AGV-01", "nodo": "H"}]


@dataclass
class ConfigApp:
    db_path: str = field(default_factory=lambda: os.environ.get("AGV_DB", "agv_gestion.db"))
    modo_agv: str = field(default_factory=lambda: os.environ.get("AGV_MODO", "simulado"))  # simulado | mqtt
    factor_tiempo: float = field(default_factory=lambda: float(os.environ.get("AGV_FACTOR_TIEMPO", "1.0")))
    api_key: str = field(default_factory=lambda: os.environ.get("AGV_API_KEY", ""))
    mqtt_host: str = field(default_factory=lambda: os.environ.get("AGV_MQTT_HOST", "broker.hivemq.com"))
    mqtt_port: int = field(default_factory=lambda: int(os.environ.get("AGV_MQTT_PORT", "1883")))
    mqtt_prefijo: str = field(default_factory=lambda: os.environ.get("AGV_MQTT_PREFIJO", "unad/agv-pg"))
