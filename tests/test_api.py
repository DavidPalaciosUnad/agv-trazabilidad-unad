"""Pruebas de integración de la API REST del módulo de gestión (gemelo digital síncrono)."""
import pytest

from gestion.app import crear_app
from gestion.config import ConfigApp


@pytest.fixture()
def cliente(tmp_path):
    app = crear_app(ConfigApp(db_path=str(tmp_path / "t.db"), modo_agv="simulado"), iniciar_hilo=False, semilla=7)
    app.testing = True
    return app.test_client(), app.config["SISTEMA"]


def nueva(c, **kw):
    datos = {"origen": "B", "destino": "E2", "masa_kg": 20, "solicitante": "OP-01"}
    datos.update(kw)
    return c.post("/api/ordenes", json=datos)


def test_crear_despachar_y_completar_orden(cliente):
    c, s = cliente
    r = nueva(c)
    assert r.status_code == 201 and r.get_json()["codigo"] == "OT-00001"
    s.avanzar(1.0)
    assert c.get("/api/ordenes/1").get_json()["estado"] == "EN_CURSO"
    s.avanzar(90.0)
    o = c.get("/api/ordenes/1").get_json()
    assert o["estado"] == "COMPLETADA" and o["distancia_m"] == pytest.approx(18.0)
    ind = c.get("/api/indicadores").get_json()
    assert ind["traslados_manuales_evitados"] == 1 and ind["masa_transportada_kg"] == 20
    tipos = [e["tipo"] for e in c.get("/api/eventos?orden_id=1").get_json()]
    for t in ("ORDEN_CREADA", "ORDEN_ASIGNADA", "ORDEN_RECIBIDA", "CARGA_COMPLETADA", "ORDEN_COMPLETADA"):
        assert t in tipos
    assert c.get("/api/trazabilidad/verificar").get_json()["integra"]


@pytest.mark.parametrize("campos,mensaje", [
    ({"origen": "B", "destino": "B"}, "diferentes"),
    ({"masa_kg": 80}, "masa"),
    ({"masa_kg": -1}, "masa"),
    ({"origen": "X"}, "inexistente"),
    ({"solicitante": "Juan Pérez"}, "código de rol"),
    ({"prioridad": 9}, "Prioridad"),
])
def test_validacion_de_entradas(cliente, campos, mensaje):
    c, _ = cliente
    r = nueva(c, **campos)
    assert r.status_code == 400 and mensaje in r.get_json()["error"]


def test_prioridad_en_el_despacho(cliente):
    c, s = cliente
    nueva(c, prioridad=3)
    nueva(c, origen="E3", destino="D", prioridad=1)
    s.avanzar(0.5)
    estados = {o["codigo"]: o["estado"] for o in c.get("/api/ordenes").get_json()}
    assert estados["OT-00002"] == "EN_CURSO" and estados["OT-00001"] == "PENDIENTE"


def test_cancelacion(cliente):
    c, s = cliente
    nueva(c)
    s.avanzar(2.0)
    r = c.post("/api/ordenes/1/cancelar")
    assert r.get_json()["estado"] == "CANCELADA"
    assert c.post("/api/ordenes/1/cancelar").status_code == 400
    s.avanzar(1.0)
    assert s.agvs["AGV-01"].logica.estado.value == "REPOSO"


def test_obstaculo_emergencia_y_rearme(cliente):
    c, s = cliente
    nueva(c)
    s.avanzar(4.0)
    c.post("/api/simulacion/obstaculo", json={"agv": "AGV-01", "distancia_m": 0.8, "duracion_s": 3})
    s.avanzar(1.5)
    assert c.get("/api/estado").get_json()["agvs"][0]["st"] == "DETENIDO_OBSTACULO"
    s.avanzar(5.0)
    c.post("/api/agv/AGV-01/emergencia")
    s.avanzar(1.0)
    assert c.get("/api/estado").get_json()["agvs"][0]["st"] == "PARADA_EMERGENCIA"
    assert c.post("/api/agv/AGV-01/rearme").get_json()["ok"]
    s.avanzar(90.0)
    assert c.get("/api/ordenes/1").get_json()["estado"] == "COMPLETADA"
    ind = c.get("/api/indicadores").get_json()
    assert ind["paradas_por_obstaculo"] == 1 and ind["paradas_de_emergencia"] == 1


def test_niosh_y_exportacion(cliente):
    c, _ = cliente
    r = c.post("/api/niosh", json={"tarea": "T1", "L": 23, "H": 25, "V": 75, "D": 25, "A": 0, "F": 0.2,
                                   "duracion_h": 1, "agarre": "bueno", "momento": "LINEA_BASE"})
    assert r.status_code == 201 and r.get_json()["RWL"] == pytest.approx(23.0)
    assert c.post("/api/niosh", json={"L": "abc"}).status_code == 400
    nueva(c)
    csv = c.get("/api/exportar/ordenes.csv").get_data(as_text=True)
    assert csv.splitlines()[0].startswith("id,codigo,origen")
    assert c.get("/api/exportar/usuarios.csv").status_code == 400


def test_clave_api_obligatoria_si_esta_configurada(tmp_path):
    app = crear_app(ConfigApp(db_path=str(tmp_path / "k.db"), api_key="secreto"), iniciar_hilo=False)
    c = app.test_client()
    assert nueva(c).status_code == 401
    r = c.post("/api/ordenes", json={"origen": "B", "destino": "E1", "masa_kg": 5, "solicitante": "OP-01"},
               headers={"X-API-Key": "secreto"})
    assert r.status_code == 201
    assert c.get("/api/ordenes").status_code == 200   # lectura sin clave
