"""Simulación del seguimiento de línea del AGV (modelo diferencial) y sintonía del PID.

Modelo: robot diferencial con dinámica de primer orden en las ruedas
(constante de tiempo TAU), arreglo de sensores IR adelantado LS metros
respecto del eje, medición del desplazamiento lateral con ruido gaussiano,
saturación en +/-0,04 m y cuantización de 2,5 mm. El error normalizado es
e = y_s / 0,04, el mismo que recibe el firmware (agv_core.cpp).
Se incluyen dos perturbaciones: desbalance del 3 % entre motores y ruido de
giro por irregularidades del piso.
Ley de control: w = -(Kp·e + Ki·∫e dt + Kd·de/dt).

Uso:  python simulacion/seguimiento_linea.py   (genera figura y resultados JSON)
"""
import json
import math
import os
import random

import numpy as np

DT = 0.02          # s, periodo del lazo de control (50 Hz)
TAU = 0.12         # s, constante de tiempo de los motorreductores
LS = 0.15          # m, adelanto del arreglo de sensores respecto del eje
B = 0.40           # m, trocha
SAT = 0.04         # m, semiancho útil del arreglo
SIGMA = 0.002      # m, ruido de medición
Q = 0.0025         # m, resolución del arreglo
R_CURVA = 1.0      # m, radio mínimo de curva de la guía (requisito de instalación)
DESBALANCE = 0.03  # 3 % de diferencia de ganancia entre motores (perturbación)
SIGMA_W = 0.05     # rad/s, perturbación aleatoria de giro (irregularidades del piso)

SALIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resultados")


def trayectoria():
    """Recta 4 m -> curva izquierda 90° (R=1 m) -> recta 3 m -> curva derecha 90° -> recta 3 m."""
    pts = []
    for x in np.arange(0, 4, 0.005):
        pts.append((x, 0.0))
    cx, cy = 4.0, R_CURVA
    for a in np.arange(-math.pi / 2, 0, 0.005 / R_CURVA):
        pts.append((cx + R_CURVA * math.cos(a), cy + R_CURVA * math.sin(a)))
    for y in np.arange(R_CURVA, R_CURVA + 3, 0.005):
        pts.append((4 + R_CURVA, y))
    cx, cy = 4 + 2 * R_CURVA, R_CURVA + 3
    for a in np.arange(math.pi, math.pi / 2, -0.005 / R_CURVA):
        pts.append((cx + R_CURVA * math.cos(a), cy + R_CURVA * math.sin(a)))
    for x in np.arange(cx, cx + 3, 0.005):
        pts.append((x, cy + R_CURVA))
    P = np.array(pts)
    seg = np.diff(P, axis=0)
    long_acum = np.concatenate([[0], np.cumsum(np.hypot(seg[:, 0], seg[:, 1]))])
    return P, long_acum


P, SACUM = trayectoria()
TANG = np.vstack([np.diff(P, axis=0), np.diff(P, axis=0)[-1:]])
TANG = TANG / np.hypot(TANG[:, 0], TANG[:, 1])[:, None]


def desplazamiento(x, y):
    """Distancia lateral con signo (+ a la izquierda de la guía) y abscisa curvilínea."""
    d2 = (P[:, 0] - x) ** 2 + (P[:, 1] - y) ** 2
    i = int(np.argmin(d2))
    tx, ty = TANG[i]
    cruz = tx * (y - P[i, 1]) - ty * (x - P[i, 0])
    return cruz, SACUM[i]


def simular(kp, kd, v=0.5, y0=0.0, th0=0.0, semilla=1, guardar=False, ki=0.0):
    rng = random.Random(semilla)
    x, y, th = 0.0, y0, th0
    vl = vr = 0.0
    e_prev = 0.0
    integ = 0.0
    t = 0.0
    hist = {"t": [], "s": [], "e_eje": [], "e_sensor": [], "w": []}
    perdida = False
    s_fin = SACUM[-1] - 0.3
    while t < 150:
        xs, ys = x + LS * math.cos(th), y + LS * math.sin(th)
        ys_real, s_path = desplazamiento(xs, ys)
        if abs(ys_real) > SAT:
            perdida = True
            break
        med = max(-SAT, min(SAT, ys_real + rng.gauss(0, SIGMA)))
        med = round(med / Q) * Q
        e = med / SAT
        integ = max(-0.5, min(0.5, integ + e * DT))
        w = -(kp * e + ki * integ + kd * (e - e_prev) / DT)
        e_prev = e
        vl_cmd, vr_cmd = v - w * B / 2, v + w * B / 2
        vl += (vl_cmd * (1 - DESBALANCE / 2) - vl) * DT / TAU
        vr += (vr_cmd * (1 + DESBALANCE / 2) - vr) * DT / TAU
        v_real, w_real = (vl + vr) / 2, (vr - vl) / B + rng.gauss(0, SIGMA_W)
        x += v_real * math.cos(th) * DT
        y += v_real * math.sin(th) * DT
        th += w_real * DT
        t += DT
        e_eje, s_eje = desplazamiento(x, y)
        if guardar:
            hist["t"].append(t); hist["s"].append(s_eje); hist["e_eje"].append(e_eje)
            hist["e_sensor"].append(ys_real); hist["w"].append(w)
        else:
            hist["e_eje"].append(e_eje)
        if s_eje >= s_fin:
            break
    arr = np.array(hist["e_eje"]) if hist["e_eje"] else np.array([1.0])
    res = {"kp": kp, "ki": ki, "kd": kd, "v": v, "perdida_de_linea": perdida,
           "rms_mm": float(np.sqrt(np.mean(arr ** 2)) * 1000),
           "max_mm": float(np.max(np.abs(arr)) * 1000), "tiempo_s": round(t, 2)}
    return (res, hist) if guardar else res


def sintonizar():
    mejores = []
    for kp in np.arange(0.5, 6.01, 0.5):
        for kd in np.arange(0.0, 0.401, 0.04):
            for ki in (0.0, 0.5, 1.0):
                r = simular(round(kp, 2), round(kd, 3), ki=ki)
                if not r["perdida_de_linea"]:
                    # criterio: error máximo (requisito) y luego RMS
                    mejores.append((r["max_mm"] + 0.5 * r["rms_mm"], r))
    mejores.sort(key=lambda z: z[0])
    return mejores[0][1], len(mejores)


if __name__ == "__main__":
    os.makedirs(SALIDA, exist_ok=True)
    mejor, factibles = sintonizar()
    kp, kd, ki = mejor["kp"], mejor["kd"], mejor["ki"]
    escenarios = {
        "nominal_0.5": simular(kp, kd, v=0.5, ki=ki),
        "reducida_0.2": simular(kp, kd, v=0.2, ki=ki),
        "offset_inicial_20mm": simular(kp, kd, v=0.5, y0=0.02, ki=ki),
        "rumbo_inicial_5grados": simular(kp, kd, v=0.5, th0=math.radians(5), ki=ki),
        "sin_derivativo_kd0": simular(kp, 0.0, v=0.5, ki=ki),
        "ganancia_baja_kp1": simular(1.0, kd, v=0.5, ki=ki),
    }
    robustez = [simular(kp, kd, v=0.5, semilla=s, ki=ki) for s in range(1, 31)]
    resumen = {"ganancias": {"kp": kp, "kd": kd, "ki": ki}, "combinaciones_evaluadas": 12 * 11 * 3,
               "combinaciones_factibles": factibles,
               "escenarios": escenarios,
               "robustez_30_semillas": {
                   "perdidas_de_linea": sum(r["perdida_de_linea"] for r in robustez),
                   "rms_mm_media": float(np.mean([r["rms_mm"] for r in robustez])),
                   "max_mm_peor": float(np.max([r["max_mm"] for r in robustez]))}}
    with open(os.path.join(SALIDA, "seguimiento_linea.json"), "w", encoding="utf-8") as f:
        json.dump(resumen, f, indent=2, ensure_ascii=False)
    print(json.dumps(resumen, indent=2, ensure_ascii=False))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _, h = simular(kp, kd, v=0.5, guardar=True, ki=ki)
    _, h2 = simular(kp, kd, v=0.5, y0=0.02, th0=math.radians(5), guardar=True, ki=ki)
    fig, ax = plt.subplots(figsize=(9, 3.6), dpi=200)
    ax.plot(h["s"], np.array(h["e_eje"]) * 1000, color="#0B2545", lw=1.4, label="Arranque centrado")
    ax.plot(h2["s"], np.array(h2["e_eje"]) * 1000, color="#E8A33D", lw=1.4,
            label="Arranque con 20 mm y 5° de desviación")
    for s0, s1 in [(4.0, 4.0 + math.pi / 2), (4 + math.pi / 2 + 3, 4 + math.pi + 3)]:
        ax.axvspan(s0, s1, color="#D5DDE5", alpha=0.6, lw=0)
    ax.axhline(25, color="#C0392B", ls="--", lw=1); ax.axhline(-25, color="#C0392B", ls="--", lw=1)
    ax.text(0.1, 26.5, "Límite de diseño ±25 mm", color="#C0392B", fontsize=8)
    ax.set_xlabel("Distancia recorrida sobre la guía (m)")
    ax.set_ylabel("Desviación lateral del eje (mm)")
    ax.set_ylim(-35, 35)
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right", fontsize=8, frameon=True, framealpha=0.9)
    ax.text(4.25, -31, "curva R = 1 m", fontsize=8, color="#5B6770")
    ax.text(4 + math.pi / 2 + 3.25, -31, "curva R = 1 m", fontsize=8, color="#5B6770")
    fig.tight_layout()
    fig.savefig(os.path.join(SALIDA, "fig_seguimiento_linea.png"))
    print("Figura guardada")
