"""Lógica de control del AGV (réplica en Python del núcleo del firmware).

La máquina de estados y las reglas de seguridad son las mismas que ejecuta
el ESP32 (firmware/agv_esp32/agv_core.cpp). Aquí se usan para el gemelo
digital: el AGV virtual recorre la planta sobre la guía con un modelo
cinemático unidimensional (posición s sobre el tramo) con límites de
aceleración y frenado.
"""
import random
from enum import Enum
from typing import Callable, List, Optional

from .config import PARAM, ParametrosAGV
from .protocolo import Orden


class Estado(str, Enum):
    REPOSO = "REPOSO"
    EN_RUTA = "EN_RUTA"
    EN_ESTACION = "EN_ESTACION"
    DETENIDO_OBSTACULO = "DETENIDO_OBSTACULO"
    PARADA_EMERGENCIA = "PARADA_EMERGENCIA"


class Zona(str, Enum):
    LIBRE = "LIBRE"
    ADVERTENCIA = "ADVERTENCIA"
    PROTECCION = "PROTECCION"


class AGVLogica:
    """Máquina de estados del AGV, independiente del hardware."""

    def __init__(self, agv_id: str, nodo: str, p: ParametrosAGV = PARAM,
                 emitir: Optional[Callable[[str, dict], None]] = None):
        self.id = agv_id
        self.p = p
        self.estado = Estado.REPOSO
        self.zona = Zona.LIBRE
        self.nodo = nodo              # último nodo alcanzado
        self.orden: Optional[Orden] = None
        self.k = 0                    # índice del segmento en curso (0-based)
        self.s = 0.0                  # m recorridos dentro del segmento
        self.v = 0.0                  # m/s
        self.bateria = 100.0
        self.t_despejado = 0.0
        self.t_en_estacion = 0.0
        self.t_sin_latido = 0.0
        self.modo_seguro_com = False
        self.estado_previo_emergencia = Estado.REPOSO
        self.distancia_recorrida = 0.0
        self._emitir = emitir or (lambda tipo, det: None)

    # ------------------------------------------------------------------ API
    def recibir_orden(self, o: Orden) -> bool:
        if self.estado not in (Estado.REPOSO,):
            self._emitir("ORDEN_RECHAZADA", {"orden": o.id, "motivo": "AGV ocupado"})
            return False
        if self.bateria < self.p.bateria_min_orden:
            self._emitir("ORDEN_RECHAZADA", {"orden": o.id, "motivo": "batería baja",
                                            "bateria": round(self.bateria, 1)})
            return False
        if o.nodo0 != self.nodo:
            self._emitir("ORDEN_RECHAZADA", {"orden": o.id, "motivo": "nodo inicial no coincide"})
            return False
        self.orden, self.k, self.s = o, 0, 0.0
        self._emitir("ORDEN_RECIBIDA", {"orden": o.id, "segmentos": len(o.segmentos)})
        if o.k_carga == 0:
            self._entrar_estacion("CARGA")
        else:
            self._cambiar(Estado.EN_RUTA)
        return True

    def cancelar(self, oid: int) -> bool:
        if self.orden and self.orden.id == oid:
            self._emitir("ORDEN_CANCELADA_AGV", {"orden": oid, "nodo": self.nodo})
            self.orden = None
            self.v = 0.0
            if self.estado != Estado.PARADA_EMERGENCIA:
                self._cambiar(Estado.REPOSO)
            return True
        return False

    def latido(self):
        self.t_sin_latido = 0.0
        if self.modo_seguro_com:
            self.modo_seguro_com = False
            self._emitir("COMUNICACION_RESTABLECIDA", {})

    def emergencia(self):
        if self.estado != Estado.PARADA_EMERGENCIA:
            self.estado_previo_emergencia = self.estado
            self._cambiar(Estado.PARADA_EMERGENCIA)

    def rearmar(self) -> bool:
        """El rearme es manual y explícito (RS-04)."""
        if self.estado != Estado.PARADA_EMERGENCIA:
            return False
        self._emitir("REARME", {})
        if self.orden is None:
            self._cambiar(Estado.REPOSO)
        elif self.estado_previo_emergencia == Estado.EN_ESTACION:
            self._cambiar(Estado.EN_ESTACION)
        else:
            self._cambiar(Estado.EN_RUTA)
        return True

    # -------------------------------------------------------------- control
    HISTERESIS = 0.05  # m, evita conmutaciones repetidas por ruido del sensor

    def zona_por_distancia(self, d: float) -> Zona:
        if d < self.p.d_proteccion:
            return Zona.PROTECCION
        limite = self.p.d_advertencia + (self.HISTERESIS if self.zona != Zona.LIBRE else 0.0)
        if d < limite:
            return Zona.ADVERTENCIA
        return Zona.LIBRE

    def velocidad_objetivo(self) -> float:
        if self.estado != Estado.EN_RUTA:
            return 0.0
        v = self.p.v_nominal
        if self.zona == Zona.ADVERTENCIA or self.modo_seguro_com:
            v = self.p.v_reducida
        # Aproximación a la siguiente parada (carga/descarga): perfil de frenado
        # v = sqrt(2·a·d) para detenerse exactamente sobre el nodo.
        restante = self.distancia_a_parada()
        v_aprox = (2 * self.p.a_frenado * max(restante, 0.0)) ** 0.5
        return min(v, max(v_aprox, 0.05))

    def distancia_a_parada(self) -> float:
        o = self.orden
        paradas = [i for i in (o.k_carga, o.k_descarga) if i > self.k]
        destino = min(paradas) if paradas else len(o.segmentos)
        d = o.segmentos[self.k][1] - self.s
        for j in range(self.k + 1, destino):
            d += o.segmentos[j][1]
        return d

    def paso(self, dt: float, d_obstaculo: float = 99.0):
        """Avanza la lógica dt segundos con la lectura de distancia frontal (m)."""
        p = self.p
        self.t_sin_latido += dt
        if self.t_sin_latido > p.t_watchdog_com and not self.modo_seguro_com and self.orden:
            self.modo_seguro_com = True
            self._emitir("FALLA_COMUNICACION", {"orden": self.orden.id})
        zona_previa = self.zona
        self.zona = self.zona_por_distancia(d_obstaculo)
        if (self.zona == Zona.ADVERTENCIA and zona_previa == Zona.LIBRE
                and self.estado == Estado.EN_RUTA and self.orden):
            self._emitir("VELOCIDAD_REDUCIDA", {"orden": self.orden.id, "distancia_m": round(d_obstaculo, 3)})

        if self.estado == Estado.PARADA_EMERGENCIA:
            pass  # el frenado de emergencia se aplica en la dinámica longitudinal
        elif self.estado == Estado.EN_RUTA:
            if self.zona == Zona.PROTECCION:
                self._cambiar(Estado.DETENIDO_OBSTACULO)
                self._emitir("OBSTACULO_DETECTADO", {"orden": self.orden.id,
                                                     "distancia_m": round(d_obstaculo, 3)})
                self.t_despejado = 0.0
        elif self.estado == Estado.DETENIDO_OBSTACULO:
            if self.zona == Zona.PROTECCION:
                self.t_despejado = 0.0
            else:
                self.t_despejado += dt
                if self.t_despejado >= p.t_reanudar:
                    self._emitir("OBSTACULO_DESPEJADO", {"orden": self.orden.id})
                    self._cambiar(Estado.EN_RUTA)
        elif self.estado == Estado.EN_ESTACION:
            self.t_en_estacion += dt
            if self.t_en_estacion >= p.t_estacion:
                self._salir_estacion()

        # Dinámica longitudinal con límites de aceleración/frenado
        v_obj = self.velocidad_objetivo()
        frenado = p.a_emergencia if self.estado == Estado.PARADA_EMERGENCIA else p.a_frenado
        if self.v < v_obj:
            self.v = min(v_obj, self.v + p.a_aceleracion * dt)
        else:
            self.v = max(v_obj, self.v - frenado * dt)
        # El vehículo sigue desplazándose mientras frena (en cualquier estado con orden)
        if self.orden and self.v > 0.0 and self.k < len(self.orden.segmentos):
            ds = self.v * dt
            self.s += ds
            self.distancia_recorrida += ds
            self.bateria = max(0.0, self.bateria - p.consumo_por_metro * ds)
            L = self.orden.segmentos[self.k][1]
            if self.s >= L - 1e-3:
                self._llegar_nodo()
        self.bateria = max(0.0, self.bateria - p.consumo_reposo * dt)

    # ------------------------------------------------------------ internos
    def _llegar_nodo(self):
        o = self.orden
        L = o.segmentos[self.k][1]
        self.nodo = o.segmentos[self.k][0]
        idx = self.k + 1          # 1-based
        self._emitir("LLEGADA_NODO", {"orden": o.id, "nodo": self.nodo})
        self.k = idx              # índice del siguiente segmento por recorrer
        if idx == o.k_descarga:
            self.s, self.v = 0.0, 0.0
            self._entrar_estacion("DESCARGA")
        elif idx == o.k_carga:
            self.s, self.v = 0.0, 0.0
            self._entrar_estacion("CARGA")
        else:
            self.s = max(0.0, self.s - L)   # nodo de paso: conserva la velocidad

    def _entrar_estacion(self, tipo: str):
        self.tipo_estacion = tipo
        self.t_en_estacion = 0.0
        self._cambiar(Estado.EN_ESTACION)
        self._emitir(f"{tipo}_INICIADA", {"orden": self.orden.id, "nodo": self.nodo})

    def _salir_estacion(self):
        o = self.orden
        self._emitir(f"{self.tipo_estacion}_COMPLETADA", {"orden": o.id, "nodo": self.nodo})
        if self.tipo_estacion == "DESCARGA":
            self._emitir("ORDEN_COMPLETADA", {"orden": o.id, "nodo": self.nodo})
            self.orden = None
            self._cambiar(Estado.REPOSO)
        else:
            self._cambiar(Estado.EN_RUTA)

    def _cambiar(self, nuevo: Estado):
        if nuevo != self.estado:
            previo = self.estado
            self.estado = nuevo
            self._emitir("CAMBIO_ESTADO", {"de": previo.value, "a": nuevo.value,
                                           "orden": self.orden.id if self.orden else None})

    def telemetria(self) -> dict:
        sig = None
        if self.orden and self.k < len(self.orden.segmentos):
            sig = self.orden.segmentos[self.k][0]
        return {"agv": self.id, "st": self.estado.value, "zona": self.zona.value,
                "ord": self.orden.id if self.orden else None, "nodo": self.nodo,
                "sig": sig, "s": round(self.s, 3), "v": round(self.v, 3),
                "bat": round(self.bateria, 1)}


class SensorUltrasonicoSimulado:
    """Modelo simple de HC-SR04: ruido gaussiano, cuantización y periodo de muestreo."""

    def __init__(self, sigma_m: float = 0.01, periodo_s: float = 0.06,
                 rango_max_m: float = 4.0, semilla: Optional[int] = None):
        self.sigma = sigma_m
        self.periodo = periodo_s
        self.rango_max = rango_max_m
        self.rng = random.Random(semilla)
        self._t = 0.0
        self._ultima = rango_max_m

    def leer(self, d_real: float, dt: float) -> float:
        self._t += dt
        if self._t >= self.periodo:
            self._t = 0.0
            if d_real >= self.rango_max:
                self._ultima = self.rango_max
            else:
                med = d_real + self.rng.gauss(0.0, self.sigma)
                self._ultima = max(0.02, round(med, 2))   # resolución ~1 cm
        return self._ultima
