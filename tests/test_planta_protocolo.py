"""Pruebas del modelo de planta (rutas) y del protocolo de mensajes."""
import pytest

from gestion.planta import Planta
from gestion.protocolo import Orden, codificar_orden, decodificar_orden


def test_ruta_mas_corta_dijkstra():
    p = Planta()
    camino, d = p.ruta_mas_corta("B", "D")
    assert camino == ["B", "E1", "D"] and d == pytest.approx(12.0)
    camino, d = p.ruta_mas_corta("H", "E3")
    assert d == pytest.approx(12.0)


def test_plan_orden_indices_de_carga_y_descarga():
    p = Planta()
    nodo0, segs, kc, kd = p.plan_orden("H", "B", "E2")
    assert nodo0 == "H" and [n for n, _ in segs] == ["B", "E1", "E2"]
    assert (kc, kd) == (1, 3)
    nodo0, segs, kc, kd = p.plan_orden("B", "B", "E1")
    assert kc == 0 and kd == 1


def test_estacion_inexistente():
    with pytest.raises(KeyError):
        Planta().ruta_mas_corta("B", "X9")


def test_protocolo_ida_y_vuelta():
    o = Orden(12, "H", [("B", 6.0), ("E1", 6.0)], 1, 2)
    txt = codificar_orden(o)
    assert txt == "ORD|12|H|B:6.00;E1:6.00|1|2"
    assert decodificar_orden(txt) == o


@pytest.mark.parametrize("msg", ["ORD|1|H|B:6.00|2|1", "ORD|1|h|B:6|1|1", "ORD|1|H|B:-1|1|1",
                                 "ORD|1|H||1|1", "XXX|1|H|B:6|1|1", "ORD|1|H|B:6"])
def test_protocolo_rechaza_mensajes_invalidos(msg):
    with pytest.raises(ValueError):
        decodificar_orden(msg)
