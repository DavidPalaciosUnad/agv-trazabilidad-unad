"""Módulo de gestión del AGV: API REST + interfaz web + gemelo digital.

Ejecución:
    python -m gestion.app            (modo simulado, http://127.0.0.1:5000)
    AGV_MODO=mqtt python -m gestion.app   (conecta con el ESP32 en Wokwi o físico)
"""
import functools
import os

from flask import Flask, Response, jsonify, request, send_from_directory

from .config import PARAM, ConfigApp
from .servicio import ErrorValidacion, SistemaGestion

BASE = os.path.dirname(os.path.abspath(__file__))


def crear_app(cfg: ConfigApp = None, iniciar_hilo: bool = True, semilla=None) -> Flask:
    cfg = cfg or ConfigApp()
    app = Flask(__name__, static_folder=os.path.join(BASE, "static"), static_url_path="/static")
    sistema = SistemaGestion(cfg, semilla=semilla)
    app.config["SISTEMA"] = sistema
    if iniciar_hilo:
        sistema.iniciar()

    def requiere_clave(f):
        """Las operaciones de escritura exigen X-API-Key si AGV_API_KEY está definida."""
        @functools.wraps(f)
        def envoltura(*a, **kw):
            if cfg.api_key and request.headers.get("X-API-Key") != cfg.api_key:
                return jsonify(error="No autorizado"), 401
            return f(*a, **kw)
        return envoltura

    @app.errorhandler(ErrorValidacion)
    def _err_validacion(e):
        return jsonify(error=str(e)), 400

    @app.after_request
    def _cabeceras(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Cache-Control"] = "no-store"
        return resp

    def cuerpo():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ErrorValidacion("Se esperaba un cuerpo JSON")
        return data

    @app.get("/")
    def inicio():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/planta")
    def planta():
        d = sistema.planta.a_dict()
        d["parametros"] = {"v_nominal": PARAM.v_nominal, "v_reducida": PARAM.v_reducida,
                           "d_advertencia": PARAM.d_advertencia, "d_proteccion": PARAM.d_proteccion,
                           "carga_nominal_kg": PARAM.carga_nominal_kg}
        return jsonify(d)

    @app.get("/api/estado")
    def estado():
        return jsonify(t_sim=round(sistema.t_sim, 2), ts=sistema.ahora(), agvs=sistema.estado_agvs(),
                       indicadores=sistema.indicadores(), modo=cfg.modo_agv)

    @app.get("/api/ordenes")
    def ordenes():
        return jsonify(sistema.listar_ordenes())

    @app.post("/api/ordenes")
    @requiere_clave
    def nueva_orden():
        return jsonify(sistema.crear_orden(cuerpo())), 201

    @app.get("/api/ordenes/<int:oid>")
    def una_orden(oid):
        o = sistema.obtener_orden(oid)
        return (jsonify(o), 200) if o else (jsonify(error="No existe"), 404)

    @app.post("/api/ordenes/<int:oid>/cancelar")
    @requiere_clave
    def cancelar(oid):
        return jsonify(sistema.cancelar_orden(oid))

    @app.get("/api/eventos")
    def eventos():
        oid = request.args.get("orden_id", type=int)
        lim = min(request.args.get("limite", default=100, type=int), 1000)
        if oid:
            filas = sistema.db.todos("SELECT * FROM eventos WHERE orden_id=? ORDER BY id", (oid,))
        else:
            filas = sistema.db.todos("SELECT * FROM eventos ORDER BY id DESC LIMIT ?", (lim,))
        return jsonify(filas)

    @app.get("/api/trazabilidad/verificar")
    def verificar():
        return jsonify(sistema.verificar_trazabilidad())

    @app.get("/api/indicadores")
    def indicadores():
        return jsonify(sistema.indicadores())

    @app.post("/api/niosh")
    @requiere_clave
    def niosh_eval():
        return jsonify(sistema.evaluar_niosh(cuerpo())), 201

    @app.get("/api/niosh")
    def niosh_lista():
        return jsonify(sistema.listar_niosh())

    @app.post("/api/agv/<agv_id>/emergencia")
    @requiere_clave
    def emergencia(agv_id):
        sistema.emergencia(agv_id)
        return jsonify(ok=True)

    @app.post("/api/agv/<agv_id>/rearme")
    @requiere_clave
    def rearme(agv_id):
        return jsonify(ok=sistema.rearmar(agv_id))

    @app.post("/api/simulacion/obstaculo")
    @requiere_clave
    def obstaculo():
        d = cuerpo()
        try:
            dist = float(d.get("distancia_m", 1.5))
            dur = float(d.get("duracion_s", 4.0))
        except (TypeError, ValueError):
            raise ErrorValidacion("Parámetros numéricos inválidos")
        sistema.simular_obstaculo(str(d.get("agv", "AGV-01")), dist, dur)
        return jsonify(ok=True)

    @app.get("/api/exportar/<tabla>.csv")
    def exportar(tabla):
        contenido = sistema.exportar_csv(tabla)
        return Response(contenido, mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={tabla}.csv"})

    return app


if __name__ == "__main__":
    puerto = int(os.environ.get("PORT", "5000"))
    crear_app().run(host="127.0.0.1", port=puerto, debug=False, use_reloader=False)
