"""Prueba de integración extremo a extremo por MQTT.

Levanta un broker MQTT local (amqtt), arranca el módulo de gestión en modo
'mqtt' y un AGV emulado que reproduce el comportamiento del firmware
(mismo protocolo de comandos, telemetría y eventos). Verifica que una orden
creada en la API llegue al AGV, se ejecute y quede trazada.
Se omite si amqtt no está instalado.
"""
import asyncio
import socket
import threading
import time

import pytest

amqtt_broker = pytest.importorskip("amqtt.broker")
mqtt = pytest.importorskip("paho.mqtt.client")

from gestion.agv import AGVLogica  # noqa: E402
from gestion.app import crear_app  # noqa: E402
from gestion.config import ConfigApp  # noqa: E402
from gestion.protocolo import decodificar_orden, telemetria_json  # noqa: E402


def _puerto_libre():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class BrokerLocal:
    def __init__(self, puerto):
        self.puerto = puerto
        self.loop = asyncio.new_event_loop()
        self.listo = threading.Event()
        self.hilo = threading.Thread(target=self._correr, daemon=True)

    def _correr(self):
        asyncio.set_event_loop(self.loop)
        cfg = {"listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{self.puerto}"}},
               "sys_interval": 0, "auth": {"allow-anonymous": True}, "topic-check": {"enabled": False}}
        self.broker = amqtt_broker.Broker(cfg, loop=self.loop) if "loop" in amqtt_broker.Broker.__init__.__code__.co_varnames else amqtt_broker.Broker(cfg)
        self.loop.run_until_complete(self.broker.start())
        self.listo.set()
        self.loop.run_forever()

    def iniciar(self):
        self.hilo.start()
        assert self.listo.wait(10), "El broker MQTT local no inició"

    def detener(self):
        fut = asyncio.run_coroutine_threadsafe(self.broker.shutdown(), self.loop)
        try:
            fut.result(5)
        except Exception:
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)


class AGVEmulado:
    """Emula el firmware: recibe comandos, ejecuta la lógica y publica telemetría y eventos."""

    def __init__(self, puerto, prefijo):
        self.base = f"{prefijo}/AGV-01"
        self.cola = []
        self.logica = AGVLogica("AGV-01", "H", emitir=self._evento)
        self.c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="agv-emulado")
        self.c.on_message = self._mensaje
        self.c.connect("127.0.0.1", puerto)
        self.c.subscribe(f"{self.base}/cmd", qos=1)
        self.c.loop_start()
        self.activo = True
        self.hilo = threading.Thread(target=self._lazo, daemon=True)
        self.hilo.start()

    def _evento(self, tipo, det):
        if tipo != "CAMBIO_ESTADO":
            self.cola.append(dict(det, ev=tipo, agv="AGV-01"))

    def _mensaje(self, c, u, msg):
        txt = msg.payload.decode()
        if txt.startswith("ORD|"):
            self.logica.recibir_orden(decodificar_orden(txt))
        elif txt.startswith("PING|"):
            self.logica.latido()

    def _lazo(self):
        t_tel = 0.0
        while self.activo:
            for _ in range(10):                 # 10 pasos de 50 ms por iteración (x10 tiempo real)
                self.logica.latido()
                self.logica.paso(0.05, 99.0)
            while self.cola:
                self.c.publish(f"{self.base}/evento", telemetria_json(self.cola.pop(0)), qos=1)
            t_tel += 0.5
            if t_tel >= 1.0:
                t_tel = 0.0
                t = self.logica.telemetria()
                t["d"] = 4.0
                self.c.publish(f"{self.base}/telemetria", telemetria_json(t))
            time.sleep(0.05)

    def detener(self):
        self.activo = False
        self.c.loop_stop()
        self.c.disconnect()


def test_orden_extremo_a_extremo_por_mqtt(tmp_path):
    puerto = _puerto_libre()
    broker = BrokerLocal(puerto)
    broker.iniciar()
    prefijo = "prueba/agv"
    agv = AGVEmulado(puerto, prefijo)
    cfg = ConfigApp(db_path=str(tmp_path / "m.db"), modo_agv="mqtt", mqtt_host="127.0.0.1",
                    mqtt_port=puerto, mqtt_prefijo=prefijo)
    app = crear_app(cfg, iniciar_hilo=True)
    c = app.test_client()
    sistema = app.config["SISTEMA"]
    try:
        time.sleep(1.5)  # conexión del cliente MQTT del módulo de gestión
        r = c.post("/api/ordenes", json={"origen": "B", "destino": "E1", "masa_kg": 12, "solicitante": "OP-02"})
        assert r.status_code == 201
        estado = None
        for _ in range(120):
            estado = c.get("/api/ordenes/1").get_json()["estado"]
            if estado == "COMPLETADA":
                break
            time.sleep(0.25)
        assert estado == "COMPLETADA"
        tipos = [e["tipo"] for e in c.get("/api/eventos?orden_id=1").get_json()]
        assert "ORDEN_RECIBIDA" in tipos and "ORDEN_COMPLETADA" in tipos
        assert c.get("/api/trazabilidad/verificar").get_json()["integra"]
    finally:
        sistema.detener()
        agv.detener()
        for a in sistema.agvs.values():
            a.cliente.loop_stop()
        broker.detener()
