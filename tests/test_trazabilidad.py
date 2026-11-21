"""Pruebas de la cadena de trazabilidad SHA-256."""
import json

from gestion.trazabilidad import GENESIS, calcular_hash, verificar_cadena


def _cadena(n=5):
    evs, previo = [], GENESIS
    for i in range(1, n + 1):
        det = {"orden": i, "masa_kg": 10 + i}
        h = calcular_hash(previo, f"2026-11-07T10:00:0{i}", "ORDEN_CREADA", i, None, det)
        evs.append({"id": i, "ts": f"2026-11-07T10:00:0{i}", "tipo": "ORDEN_CREADA", "orden_id": i,
                    "agv_id": None, "detalle": json.dumps(det), "hash_prev": previo, "hash": h})
        previo = h
    return evs


def test_cadena_integra():
    r = verificar_cadena(_cadena())
    assert r["integra"] and r["eventos_verificados"] == 5


def test_detecta_alteracion_de_detalle():
    evs = _cadena()
    evs[2]["detalle"] = json.dumps({"orden": 3, "masa_kg": 1})
    r = verificar_cadena(evs)
    assert not r["integra"] and r["falla_en_evento"] == 3


def test_detecta_eliminacion_de_registro():
    evs = _cadena()
    del evs[1]
    r = verificar_cadena(evs)
    assert not r["integra"] and r["falla_en_evento"] == 3


def test_hash_determinista_e_independiente_del_orden_de_claves():
    a = calcular_hash(GENESIS, "t", "X", 1, "AGV-01", {"a": 1, "b": 2})
    b = calcular_hash(GENESIS, "t", "X", 1, "AGV-01", {"b": 2, "a": 1})
    assert a == b and len(a) == 64
