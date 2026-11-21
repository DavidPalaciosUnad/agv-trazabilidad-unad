"""Verificación de los campos de advertencia y protección ante obstáculos.

Usa la misma lógica del AGV (gestion/agv.py, réplica del firmware) con el
modelo del sensor ultrasónico (ruido 1 cm, periodo 60 ms). Se ejecutan dos
ensayos:
 1. Obstáculo estático a 3,0 m de la trayectoria (aproximación completa).
 2. Intrusión súbita de una persona a distintas distancias mientras el AGV
    circula a velocidad nominal (30 repeticiones por distancia).
Criterio de aceptación (RS-01/RS-02): el AGV se detiene sin contacto y con
holgura final >= 0,15 m en todos los ensayos con intrusión fuera del
campo de protección; dentro de él, la holgura debe ser positiva.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from gestion.agv import AGVLogica, Estado, SensorUltrasonicoSimulado  # noqa: E402
from gestion.config import PARAM  # noqa: E402
from gestion.protocolo import Orden  # noqa: E402

DT = 0.02
SALIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resultados")


def agv_en_marcha(semilla):
    a = AGVLogica("AGV-T", "A")
    a.recibir_orden(Orden(1, "A", [("Z", 60.0)], 0, 1))
    a.estado = Estado.EN_RUTA      # se omite la permanencia de carga inicial
    sensor = SensorUltrasonicoSimulado(semilla=semilla)
    return a, sensor


def ensayo_estatico(d_obst=3.0, semilla=1):
    a, sensor = agv_en_marcha(semilla)
    # acelera hasta régimen antes de que aparezca el obstáculo
    for _ in range(int(3 / DT)):
        a.latido(); a.paso(DT, sensor.leer(99.0, DT))
    s0 = a.distancia_recorrida
    t, hist = 0.0, {"t": [], "d": [], "v": [], "estado": []}
    while t < 12:
        d_real = d_obst - (a.distancia_recorrida - s0)
        a.latido()
        a.paso(DT, sensor.leer(d_real, DT))
        t += DT
        hist["t"].append(t); hist["d"].append(d_real); hist["v"].append(a.v); hist["estado"].append(a.estado.value)
    return hist


def ensayo_intrusion(d_intrusion, semilla):
    a, sensor = agv_en_marcha(semilla)
    for _ in range(int(3 / DT)):
        a.latido(); a.paso(DT, sensor.leer(99.0, DT))
    v_inicial = a.v
    s0 = a.distancia_recorrida
    for _ in range(int(6 / DT)):
        d_real = d_intrusion - (a.distancia_recorrida - s0)
        a.latido(); a.paso(DT, sensor.leer(d_real, DT))
        if a.v == 0.0 and a.estado == Estado.DETENIDO_OBSTACULO:
            break
    holgura = d_intrusion - (a.distancia_recorrida - s0)
    return {"v_inicial": v_inicial, "holgura_m": holgura, "detenido": a.estado == Estado.DETENIDO_OBSTACULO}


def distancia_parada_teorica(v, t_r=PARAM.t_reaccion, a=PARAM.a_frenado):
    return v * t_r + v ** 2 / (2 * a)


if __name__ == "__main__":
    os.makedirs(SALIDA, exist_ok=True)
    h = ensayo_estatico()
    d_final = h["d"][-1]
    distancias = [0.30, 0.40, 0.50, 0.60, 0.80, 1.00, 1.20, 1.50]
    tabla = []
    for d in distancias:
        res = [ensayo_intrusion(d, s) for s in range(1, 31)]
        hol = np.array([r["holgura_m"] for r in res])
        tabla.append({"d_intrusion_m": d, "repeticiones": 30,
                      "detenciones": int(sum(r["detenido"] for r in res)),
                      "holgura_min_m": round(float(hol.min()), 3),
                      "holgura_media_m": round(float(hol.mean()), 3),
                      "contactos": int((hol <= 0).sum())})
    resumen = {
        "parametros": {"v_nominal": PARAM.v_nominal, "v_reducida": PARAM.v_reducida,
                       "d_advertencia": PARAM.d_advertencia, "d_proteccion": PARAM.d_proteccion,
                       "a_frenado": PARAM.a_frenado, "t_reaccion": PARAM.t_reaccion},
        "distancia_parada_teorica_v_nominal_m": round(distancia_parada_teorica(PARAM.v_nominal), 4),
        "distancia_parada_teorica_v_reducida_m": round(distancia_parada_teorica(PARAM.v_reducida), 4),
        "ensayo_estatico": {"d_obstaculo_inicial_m": 3.0, "holgura_final_m": round(d_final, 3),
                            "v_min_en_advertencia": round(min(v for v, e, d in zip(h["v"], h["estado"], h["d"])
                                                              if 0.6 < d < 1.0), 3)},
        "ensayo_intrusion": tabla,
    }
    with open(os.path.join(SALIDA, "frenado_obstaculo.json"), "w", encoding="utf-8") as f:
        json.dump(resumen, f, indent=2, ensure_ascii=False)
    print(json.dumps(resumen, indent=2, ensure_ascii=False))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.8), dpi=200)
    t = np.array(h["t"]); d = np.array(h["d"]); v = np.array(h["v"])
    a1.plot(t, d, color="#0B2545", lw=1.6, label="Distancia al obstáculo (m)")
    a1.axhspan(0, PARAM.d_proteccion, color="#C0392B", alpha=0.12, lw=0)
    a1.axhspan(PARAM.d_proteccion, PARAM.d_advertencia, color="#E8A33D", alpha=0.15, lw=0)
    a1.text(8.2, 0.22, "campo de protección", fontsize=7.5, color="#922B21")
    a1.text(8.2, 0.80, "campo de advertencia", fontsize=7.5, color="#8A5A00")
    a1.set_xlabel("Tiempo (s)"); a1.set_ylabel("Distancia (m)"); a1.set_ylim(0, 3.2); a1.grid(alpha=0.3)
    a1b = a1.twinx()
    a1b.plot(t, v, color="#2E8B57", lw=1.4, ls="--", label="Velocidad (m/s)")
    a1b.set_ylabel("Velocidad (m/s)"); a1b.set_ylim(0, 0.6)
    a1.set_title("Aproximación a obstáculo estático", fontsize=10)
    l1, n1 = a1.get_legend_handles_labels(); l2, n2 = a1b.get_legend_handles_labels()
    a1.legend(l1 + l2, n1 + n2, fontsize=7.5, loc="upper right", frameon=False)
    xs = [r["d_intrusion_m"] for r in tabla]
    a2.bar([str(x) for x in xs], [r["holgura_min_m"] for r in tabla], color="#0B2545", label="Holgura mínima")
    a2.plot([str(x) for x in xs], [r["holgura_media_m"] for r in tabla], "o-", color="#E8A33D", label="Holgura media")
    a2.axhline(0.15, color="#C0392B", ls="--", lw=1)
    a2.text(7.45, 0.105, "holgura de diseño 0,15 m", fontsize=7.5, color="#C0392B", ha="right",
            bbox=dict(facecolor="white", edgecolor="none", pad=1.5))
    a2.set_xlabel("Distancia de intrusión súbita (m)"); a2.set_ylabel("Holgura al detenerse (m)")
    a2.set_title("Intrusión súbita a 0,5 m/s (30 ensayos por distancia)", fontsize=10)
    a2.grid(alpha=0.3, axis="y"); a2.legend(fontsize=7.5, frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(os.path.join(SALIDA, "fig_frenado_obstaculo.png"))
    print("Figura guardada")
