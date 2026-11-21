"""Capa de servicio: órdenes, despacho, trazabilidad, indicadores y gemelo digital."""
import csv
import io
import json
import threading
import time
from datetime import datetime, timedelta

from . import niosh
from .agv import AGVLogica, Estado, SensorUltrasonicoSimulado
from .config import AGVS_INICIALES, PARAM, ConfigApp
from .db import BaseDatos
from .planta import Planta
from .protocolo import Orden, codificar_orden, decodificar_orden
from .trazabilidad import GENESIS, calcular_hash, verificar_cadena

DT = 0.05  # s, paso de simulación (20 Hz, igual al lazo del firmware)
ESTADOS_ORDEN = ("PENDIENTE", "ASIGNADA", "EN_CURSO", "COMPLETADA", "CANCELADA", "FALLIDA")


class ErrorValidacion(ValueError):
    pass


class AdaptadorSimulado:
    """AGV virtual del gemelo digital: misma lógica que el firmware."""

    def __init__(self, agv_id, nodo, emitir, semilla=None):
        self.logica = AGVLogica(agv_id, nodo, PARAM, emitir)
        self.sensor = SensorUltrasonicoSimulado(semilla=semilla)
        self.obstaculos = []   # {"d0":m, "ref":dist_recorrida, "t":s restantes}
        self.d_medida = 4.0

    @property
    def id(self):
        return self.logica.id

    def enviar(self, texto: str):
        if texto.startswith("ORD|"):
            self.logica.recibir_orden(decodificar_orden(texto))
        elif texto.startswith("CAN|"):
            self.logica.cancelar(int(texto.split("|")[1]))
        elif texto.startswith("PING|"):
            self.logica.latido()

    def inyectar_obstaculo(self, distancia_m=1.5, duracion_s=4.0):
        self.obstaculos.append({"d0": distancia_m, "ref": self.logica.distancia_recorrida,
                                "t": duracion_s})

    def paso(self, dt):
        d_real = 99.0
        vivos = []
        for o in self.obstaculos:
            o["t"] -= dt
            if o["t"] > 0:
                vivos.append(o)
                d = o["d0"] - (self.logica.distancia_recorrida - o["ref"])
                if d > 0:
                    d_real = min(d_real, d)
        self.obstaculos = vivos
        self.d_medida = self.sensor.leer(d_real, dt)
        self.logica.paso(dt, self.d_medida)


class SistemaGestion:
    def __init__(self, cfg: ConfigApp = None, semilla=None):
        self.cfg = cfg or ConfigApp()
        self.db = BaseDatos(self.cfg.db_path)
        self.planta = Planta()
        self.t_sim = 0.0
        self.t0 = datetime.now().replace(microsecond=0)
        self.lock = threading.RLock()
        self._hilo = None
        self._activo = False
        self._t_ping = 0.0
        self._t_telemetria = 0.0
        self.agvs = {}
        if self.cfg.modo_agv == "mqtt":
            from .mqtt_puente import AdaptadorMQTT
            for a in AGVS_INICIALES:
                self.agvs[a["id"]] = AdaptadorMQTT(a["id"], a["nodo"], self.cfg, self._emisor(a["id"]))
        else:
            for i, a in enumerate(AGVS_INICIALES):
                s = None if semilla is None else semilla + i
                self.agvs[a["id"]] = AdaptadorSimulado(a["id"], a["nodo"], self._emisor(a["id"]), s)

    # ------------------------------------------------------------ tiempo
    def ahora(self) -> str:
        return (self.t0 + timedelta(seconds=self.t_sim)).isoformat(timespec="milliseconds")

    def iniciar(self):
        self._activo = True
        self._hilo = threading.Thread(target=self._bucle, daemon=True)
        self._hilo.start()

    def detener(self):
        self._activo = False

    def _bucle(self):
        while self._activo:
            pasos = max(1, int(round(self.cfg.factor_tiempo)))
            for _ in range(pasos):
                self.paso(DT)
            time.sleep(DT)

    def avanzar(self, segundos: float):
        """Avance síncrono del gemelo digital (pruebas y simulación por lotes)."""
        for _ in range(int(round(segundos / DT))):
            self.paso(DT)

    def paso(self, dt):
        with self.lock:
            self.t_sim += dt
            for a in self.agvs.values():
                a.paso(dt)
            self._despachar()
            self._t_ping += dt
            if self._t_ping >= 2.0:
                self._t_ping = 0.0
                for a in self.agvs.values():
                    a.enviar(f"PING|{int(self.t_sim)}")
            self._t_telemetria += dt
            if self._t_telemetria >= 1.0:
                self._t_telemetria = 0.0
                self._guardar_telemetria()

    # ------------------------------------------------------- trazabilidad
    def registrar_evento(self, tipo, orden_id=None, agv_id=None, detalle=None):
        detalle = detalle or {}
        with self.db.lock:
            ult = self.db.uno("SELECT hash FROM eventos ORDER BY id DESC LIMIT 1")
            previo = ult["hash"] if ult else GENESIS
            ts = self.ahora()
            h = calcular_hash(previo, ts, tipo, orden_id, agv_id, detalle)
            self.db.ejecutar(
                "INSERT INTO eventos (ts,tipo,orden_id,agv_id,detalle,hash_prev,hash) VALUES (?,?,?,?,?,?,?)",
                (ts, tipo, orden_id, agv_id, json.dumps(detalle, sort_keys=True, ensure_ascii=False,
                                                        separators=(",", ":")), previo, h))
        return h

    def verificar_trazabilidad(self):
        return verificar_cadena(self.db.todos("SELECT * FROM eventos ORDER BY id"))

    def _emisor(self, agv_id):
        def emitir(tipo, det):
            oid = det.get("orden")
            self.registrar_evento(tipo, oid, agv_id, det)
            if tipo == "ORDEN_RECIBIDA":
                self.db.ejecutar("UPDATE ordenes SET estado='EN_CURSO', iniciada=? WHERE id=?",
                                 (self.ahora(), oid))
            elif tipo == "ORDEN_COMPLETADA":
                self.db.ejecutar("UPDATE ordenes SET estado='COMPLETADA', completada=? WHERE id=?",
                                 (self.ahora(), oid))
            elif tipo == "ORDEN_RECHAZADA":
                self.db.ejecutar("UPDATE ordenes SET estado='PENDIENTE', agv_id=NULL, asignada=NULL "
                                 "WHERE id=? AND estado='ASIGNADA'", (oid,))
        return emitir

    # ------------------------------------------------------------ órdenes
    def crear_orden(self, datos: dict) -> dict:
        origen = str(datos.get("origen", "")).strip().upper()
        destino = str(datos.get("destino", "")).strip().upper()
        solicitante = str(datos.get("solicitante", "")).strip().upper()
        descripcion = str(datos.get("descripcion", "")).strip()[:200]
        try:
            masa = float(datos.get("masa_kg"))
            prioridad = int(datos.get("prioridad", 2))
        except (TypeError, ValueError):
            raise ErrorValidacion("masa_kg y prioridad deben ser numéricos")
        if origen not in self.planta.estaciones or destino not in self.planta.estaciones:
            raise ErrorValidacion("Origen o destino inexistente")
        if origen == destino:
            raise ErrorValidacion("Origen y destino deben ser diferentes")
        if not (0 < masa <= PARAM.carga_nominal_kg):
            raise ErrorValidacion(f"La masa debe estar entre 0 y {PARAM.carga_nominal_kg:g} kg")
        if prioridad not in (1, 2, 3):
            raise ErrorValidacion("Prioridad debe ser 1 (alta), 2 (media) o 3 (baja)")
        if not solicitante or len(solicitante) > 12 or not solicitante.replace("-", "").isalnum():
            raise ErrorValidacion("Solicitante debe ser un código de rol (p. ej. OP-01), no un nombre")
        with self.lock:
            n = self.db.uno("SELECT COUNT(*) AS n FROM ordenes")["n"] + 1
            codigo = f"OT-{n:05d}"
            ts = self.ahora()
            cur = self.db.ejecutar(
                "INSERT INTO ordenes (codigo,origen,destino,masa_kg,descripcion,solicitante,prioridad,creada) "
                "VALUES (?,?,?,?,?,?,?,?)", (codigo, origen, destino, masa, descripcion, solicitante, prioridad, ts))
            oid = cur.lastrowid
            self.registrar_evento("ORDEN_CREADA", oid, None, {
                "codigo": codigo, "origen": origen, "destino": destino, "masa_kg": masa,
                "solicitante": solicitante, "prioridad": prioridad})
        return self.obtener_orden(oid)

    def obtener_orden(self, oid):
        return self.db.uno("SELECT * FROM ordenes WHERE id=?", (oid,))

    def listar_ordenes(self, limite=200):
        return self.db.todos("SELECT * FROM ordenes ORDER BY id DESC LIMIT ?", (limite,))

    def cancelar_orden(self, oid) -> dict:
        with self.lock:
            o = self.obtener_orden(oid)
            if not o:
                raise ErrorValidacion("Orden inexistente")
            if o["estado"] in ("COMPLETADA", "CANCELADA", "FALLIDA"):
                raise ErrorValidacion("La orden ya está cerrada")
            if o["agv_id"] and o["agv_id"] in self.agvs:
                self.agvs[o["agv_id"]].enviar(f"CAN|{oid}")
            self.db.ejecutar("UPDATE ordenes SET estado='CANCELADA', completada=? WHERE id=?", (self.ahora(), oid))
            self.registrar_evento("ORDEN_CANCELADA", oid, o["agv_id"], {"estado_previo": o["estado"]})
        return self.obtener_orden(oid)

    def _despachar(self):
        for a in self.agvs.values():
            lg = a.logica
            if lg.estado != Estado.REPOSO or lg.orden is not None:
                continue
            if lg.bateria < PARAM.bateria_min_orden:
                continue
            ocupado = self.db.uno("SELECT id FROM ordenes WHERE agv_id=? AND estado IN ('ASIGNADA','EN_CURSO')",
                                  (a.id,))
            if ocupado:
                continue
            o = self.db.uno("SELECT * FROM ordenes WHERE estado='PENDIENTE' ORDER BY prioridad, id LIMIT 1")
            if not o:
                return
            nodo0, segs, kc, kd = self.planta.plan_orden(lg.nodo, o["origen"], o["destino"])
            dist = sum(d for _, d in segs)
            self.db.ejecutar("UPDATE ordenes SET estado='ASIGNADA', agv_id=?, asignada=?, distancia_m=? WHERE id=?",
                             (a.id, self.ahora(), round(dist, 3), o["id"]))
            self.registrar_evento("ORDEN_ASIGNADA", o["id"], a.id, {
                "ruta": [nodo0] + [n for n, _ in segs], "distancia_m": round(dist, 3),
                "k_carga": kc, "k_descarga": kd})
            a.enviar(codificar_orden(Orden(o["id"], nodo0, segs, kc, kd)))

    # ------------------------------------------------------- gemelo digital
    def estado_agvs(self):
        res = []
        for a in self.agvs.values():
            t = a.logica.telemetria()
            lg = a.logica
            if lg.orden and lg.k < len(lg.orden.segmentos):
                x, y = self.planta.posicion(lg.nodo, lg.orden.segmentos[lg.k][0], lg.s)
            else:
                e = self.planta.estaciones[lg.nodo]
                x, y = e["x"], e["y"]
            t.update({"x": round(x, 3), "y": round(y, 3), "d_obst": round(a.d_medida, 2),
                      "obstaculos_activos": len(getattr(a, "obstaculos", []))})
            res.append(t)
        return res

    def _guardar_telemetria(self):
        for t in self.estado_agvs():
            self.db.ejecutar(
                "INSERT INTO telemetria (ts,agv_id,estado,zona,nodo,x,y,v,d_obst,bateria) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (self.ahora(), t["agv"], t["st"], t["zona"], t["nodo"], t["x"], t["y"], t["v"], t["d_obst"], t["bat"]))

    def simular_obstaculo(self, agv_id, distancia_m=1.5, duracion_s=4.0):
        a = self._agv(agv_id)
        if not hasattr(a, "inyectar_obstaculo"):
            raise ErrorValidacion("Solo disponible en modo simulado")
        if not (0.1 <= distancia_m <= 4.0 and 0.5 <= duracion_s <= 60):
            raise ErrorValidacion("Parámetros de obstáculo fuera de rango")
        a.inyectar_obstaculo(distancia_m, duracion_s)
        self.registrar_evento("SIMULACION_OBSTACULO", None, agv_id,
                              {"distancia_m": distancia_m, "duracion_s": duracion_s})

    def emergencia(self, agv_id):
        with self.lock:
            a = self._agv(agv_id)
            a.logica.emergencia()

    def rearmar(self, agv_id):
        with self.lock:
            a = self._agv(agv_id)
            return a.logica.rearmar()

    def _agv(self, agv_id):
        if agv_id not in self.agvs:
            raise ErrorValidacion("AGV inexistente")
        return self.agvs[agv_id]

    # --------------------------------------------------------- indicadores
    def indicadores(self):
        def seg(a, b):
            return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()
        conteo = {e: 0 for e in ESTADOS_ORDEN}
        for f in self.db.todos("SELECT estado, COUNT(*) n FROM ordenes GROUP BY estado"):
            conteo[f["estado"]] = f["n"]
        comp = self.db.todos("SELECT * FROM ordenes WHERE estado='COMPLETADA'")
        masa = sum(o["masa_kg"] for o in comp)
        dist = sum(o["distancia_m"] or 0 for o in comp)
        ciclos = [seg(o["creada"], o["completada"]) for o in comp]
        ejec = [seg(o["iniciada"], o["completada"]) for o in comp if o["iniciada"]]
        ev = {f["tipo"]: f["n"] for f in self.db.todos("SELECT tipo, COUNT(*) n FROM eventos GROUP BY tipo")}
        cerradas = conteo["COMPLETADA"] + conteo["FALLIDA"] + conteo["CANCELADA"]
        return {
            "ordenes": conteo,
            "traslados_manuales_evitados": len(comp),
            "masa_transportada_kg": round(masa, 2),
            "distancia_recorrida_m": round(dist, 2),
            "tiempo_ciclo_medio_s": round(sum(ciclos) / len(ciclos), 1) if ciclos else None,
            "tiempo_ejecucion_medio_s": round(sum(ejec) / len(ejec), 1) if ejec else None,
            "tasa_exito": round(conteo["COMPLETADA"] / cerradas, 4) if cerradas else None,
            "paradas_por_obstaculo": ev.get("OBSTACULO_DETECTADO", 0),
            "reducciones_de_velocidad": ev.get("VELOCIDAD_REDUCIDA", 0),
            "paradas_de_emergencia": self._contar_emergencias(),
            "fallas_comunicacion": ev.get("FALLA_COMUNICACION", 0),
            "eventos_registrados": sum(ev.values()),
        }

    def _contar_emergencias(self):
        filas = self.db.todos("SELECT detalle FROM eventos WHERE tipo='CAMBIO_ESTADO'")
        return sum(1 for f in filas if json.loads(f["detalle"]).get("a") == "PARADA_EMERGENCIA")

    # ------------------------------------------------------------ NIOSH
    def evaluar_niosh(self, datos: dict):
        try:
            p = {k: float(datos[k]) for k in ("L", "H", "V", "D", "A", "F", "duracion_h")}
        except (KeyError, TypeError, ValueError):
            raise ErrorValidacion("Faltan parámetros numéricos L, H, V, D, A, F, duracion_h")
        agarre = str(datos.get("agarre", "regular"))
        tarea = str(datos.get("tarea", "")).strip()[:120] or "Tarea sin nombre"
        momento = str(datos.get("momento", "LINEA_BASE")).upper()
        if momento not in ("LINEA_BASE", "POSINTERVENCION"):
            raise ErrorValidacion("momento debe ser LINEA_BASE o POSINTERVENCION")
        try:
            r = niosh.calcular(agarre=agarre, **p)
        except ValueError as e:
            raise ErrorValidacion(str(e))
        self.db.ejecutar(
            "INSERT INTO evaluaciones_niosh (ts,tarea,momento,L,H,V,D,A,F,duracion_h,agarre,RWL,LI) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (self.ahora(), tarea, momento, p["L"], p["H"], p["V"], p["D"], p["A"], p["F"],
             p["duracion_h"], agarre, r.RWL, r.LI if r.LI != float("inf") else None))
        return {"tarea": tarea, "momento": momento, **r.a_dict()}

    def listar_niosh(self):
        return self.db.todos("SELECT * FROM evaluaciones_niosh ORDER BY id DESC")

    # ----------------------------------------------------------- exportar
    def exportar_csv(self, tabla: str) -> str:
        if tabla not in ("ordenes", "eventos", "telemetria", "evaluaciones_niosh"):
            raise ErrorValidacion("Tabla no exportable")
        filas = self.db.todos(f"SELECT * FROM {tabla} ORDER BY id")  # nombre validado arriba
        buf = io.StringIO()
        if filas:
            w = csv.DictWriter(buf, fieldnames=list(filas[0].keys()))
            w.writeheader()
            w.writerows(filas)
        return buf.getvalue()
