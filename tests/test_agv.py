"""Pruebas de la lógica del AGV (réplica del firmware) usada por el gemelo digital."""
from gestion.agv import AGVLogica, Estado, Zona
from gestion.protocolo import Orden

DT = 0.05


def correr(a, seg, d=99.0):
    for _ in range(int(round(seg / DT))):
        a.latido()
        a.paso(DT, d)


def test_ciclo_completo_con_eventos():
    eventos = []
    a = AGVLogica("AGV-T", "H", emitir=lambda t, d: eventos.append(t))
    assert a.recibir_orden(Orden(1, "H", [("B", 6.0), ("E1", 6.0), ("E2", 6.0)], 1, 3))
    correr(a, 80)
    assert a.estado == Estado.REPOSO and a.nodo == "E2"
    secuencia = [e for e in eventos if e != "CAMBIO_ESTADO"]
    assert secuencia == ["ORDEN_RECIBIDA", "LLEGADA_NODO", "CARGA_INICIADA", "CARGA_COMPLETADA",
                         "LLEGADA_NODO", "LLEGADA_NODO", "DESCARGA_INICIADA", "DESCARGA_COMPLETADA",
                         "ORDEN_COMPLETADA"]


def test_nodo_de_paso_sin_detenerse():
    a = AGVLogica("AGV-T", "H")
    a.recibir_orden(Orden(1, "H", [("B", 6.0), ("E1", 6.0), ("E2", 6.0)], 1, 3))
    correr(a, 18.5)            # ya cargó en B y circula hacia E1
    velocidades = []
    for _ in range(int(16 / DT)):
        a.latido(); a.paso(DT); velocidades.append((a.nodo, a.v))
    en_e1 = [v for n, v in velocidades if n == "E1"]
    assert en_e1 and max(en_e1) > 0.45   # atraviesa E1 a velocidad de crucero


def test_zonas_y_parada_por_obstaculo():
    a = AGVLogica("AGV-T", "A")
    a.recibir_orden(Orden(1, "A", [("Z", 50.0)], 1, 1))
    correr(a, 3)
    correr(a, 1, d=1.0)
    assert a.zona == Zona.ADVERTENCIA and abs(a.v - 0.2) < 1e-6
    correr(a, 1, d=0.4)
    assert a.estado == Estado.DETENIDO_OBSTACULO and a.v == 0.0
    correr(a, 2.5, d=99)
    assert a.estado == Estado.EN_RUTA


def test_emergencia_requiere_rearme_manual():
    a = AGVLogica("AGV-T", "A")
    a.recibir_orden(Orden(1, "A", [("Z", 50.0)], 1, 1))
    correr(a, 3)
    a.emergencia()
    correr(a, 2)
    assert a.estado == Estado.PARADA_EMERGENCIA and a.v == 0.0
    correr(a, 5)
    assert a.estado == Estado.PARADA_EMERGENCIA
    assert a.rearmar() and a.estado == Estado.EN_RUTA


def test_rechazos_bateria_y_ocupado():
    a = AGVLogica("AGV-T", "H")
    a.bateria = 10
    assert not a.recibir_orden(Orden(1, "H", [("B", 6.0)], 1, 1))
    b = AGVLogica("AGV-T", "H")
    assert b.recibir_orden(Orden(1, "H", [("B", 6.0)], 1, 1))
    assert not b.recibir_orden(Orden(2, "H", [("B", 6.0)], 1, 1))


def test_watchdog_de_comunicacion():
    a = AGVLogica("AGV-T", "A")
    a.recibir_orden(Orden(1, "A", [("Z", 50.0)], 1, 1))
    for _ in range(int(12 / DT)):
        a.paso(DT)                 # sin latidos
    assert a.modo_seguro_com and a.v <= 0.2 + 1e-9
