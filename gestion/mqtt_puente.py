"""Puente MQTT entre el módulo de gestión y un AGV físico o simulado en Wokwi.

El AGV publica telemetría (1 Hz) y eventos; el módulo de gestión publica
comandos. El objeto EspejoAGV reproduce el estado del AGV remoto para que el
despachador lo trate igual que al AGV del gemelo digital.
"""
import threading

import paho.mqtt.client as mqtt

from .agv import Estado, Zona
from .protocolo import decodificar_orden, leer_json


class EspejoAGV:
    def __init__(self, agv_id, nodo, publicar):
        self.id = agv_id
        self.estado = Estado.REPOSO
        self.zona = Zona.LIBRE
        self.nodo = nodo
        self.orden = None
        self.k = 0
        self.s = 0.0
        self.v = 0.0
        self.bateria = 100.0
        self._publicar = publicar

    def telemetria(self):
        sig = self.orden.segmentos[self.k][0] if self.orden and self.k < len(self.orden.segmentos) else None
        return {"agv": self.id, "st": self.estado.value, "zona": self.zona.value,
                "ord": self.orden.id if self.orden else None, "nodo": self.nodo, "sig": sig,
                "s": round(self.s, 3), "v": round(self.v, 3), "bat": round(self.bateria, 1)}

    def emergencia(self):
        self._publicar("EST|1")

    def rearmar(self):
        self._publicar("RST|1")
        return True


class AdaptadorMQTT:
    def __init__(self, agv_id, nodo, cfg, emitir):
        self.cfg = cfg
        self.base = f"{cfg.mqtt_prefijo}/{agv_id}"
        self._emitir = emitir
        self._lock = threading.Lock()
        self.d_medida = 4.0
        self.logica = EspejoAGV(agv_id, nodo, self.publicar)
        self.cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"gestion-{agv_id}")
        self.cliente.on_connect = self._al_conectar
        self.cliente.on_message = self._al_mensaje
        self.cliente.connect_async(cfg.mqtt_host, cfg.mqtt_port, keepalive=30)
        self.cliente.loop_start()

    @property
    def id(self):
        return self.logica.id

    def _al_conectar(self, cliente, userdata, flags, rc, props=None):
        cliente.subscribe(f"{self.base}/telemetria", qos=0)
        cliente.subscribe(f"{self.base}/evento", qos=1)

    def _al_mensaje(self, cliente, userdata, msg):
        try:
            data = leer_json(msg.payload)
        except ValueError:
            return  # se descartan mensajes mal formados (validación de entrada)
        with self._lock:
            if msg.topic.endswith("/telemetria"):
                lg = self.logica
                try:
                    lg.estado = Estado(data.get("st", lg.estado.value))
                    lg.zona = Zona(data.get("zona", lg.zona.value))
                except ValueError:
                    return
                lg.nodo = str(data.get("nodo", lg.nodo))[:4]
                lg.s = float(data.get("s", 0.0))
                lg.v = float(data.get("v", 0.0))
                lg.bateria = float(data.get("bat", lg.bateria))
                self.d_medida = float(data.get("d", self.d_medida))
                if data.get("ord") is None:
                    lg.orden = None
                elif lg.orden is not None:
                    sig = data.get("sig")
                    for j in range(lg.k, len(lg.orden.segmentos)):
                        if lg.orden.segmentos[j][0] == sig:
                            lg.k = j
                            break
            elif msg.topic.endswith("/evento"):
                tipo = str(data.pop("ev", "EVENTO"))[:40]
                if tipo in ("ORDEN_COMPLETADA", "ORDEN_RECHAZADA", "ORDEN_CANCELADA_AGV"):
                    self.logica.orden = None
                self._emitir(tipo, data)

    def publicar(self, texto: str):
        self.cliente.publish(f"{self.base}/cmd", texto, qos=1)

    def enviar(self, texto: str):
        if texto.startswith("ORD|"):
            o = decodificar_orden(texto)
            with self._lock:
                self.logica.orden = o
                self.logica.k = 0
        self.publicar(texto)

    def paso(self, dt):
        pass  # el AGV remoto ejecuta su propio lazo de control
