"""Ecuación revisada de levantamiento de NIOSH (Waters et al., 1993; 1994).

RWL = LC · HM · VM · DM · AM · FM · CM      (peso límite recomendado, kg)
LI  = L / RWL                               (índice de levantamiento)

Las tablas de FM y CM corresponden a las tablas 5 y 7 del manual de
aplicaciones de NIOSH (Waters et al., 1994), en unidades métricas.
"""
from bisect import bisect_left
from dataclasses import dataclass, asdict

LC = 23.0  # kg, constante de carga

# Frecuencias (levantamientos/min) de la tabla 5
_F = [0.2, 0.5, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
# Columnas: (<=1 h, V<75), (<=1 h, V>=75), (<=2 h, V<75), (<=2 h, V>=75), (<=8 h, V<75), (<=8 h, V>=75)
_FM = [
    (1.00, 1.00, 0.95, 0.95, 0.85, 0.85),
    (0.97, 0.97, 0.92, 0.92, 0.81, 0.81),
    (0.94, 0.94, 0.88, 0.88, 0.75, 0.75),
    (0.91, 0.91, 0.84, 0.84, 0.65, 0.65),
    (0.88, 0.88, 0.79, 0.79, 0.55, 0.55),
    (0.84, 0.84, 0.72, 0.72, 0.45, 0.45),
    (0.80, 0.80, 0.60, 0.60, 0.35, 0.35),
    (0.75, 0.75, 0.50, 0.50, 0.27, 0.27),
    (0.70, 0.70, 0.42, 0.42, 0.22, 0.22),
    (0.60, 0.60, 0.35, 0.35, 0.18, 0.18),
    (0.52, 0.52, 0.30, 0.30, 0.00, 0.15),
    (0.45, 0.45, 0.26, 0.26, 0.00, 0.13),
    (0.41, 0.41, 0.00, 0.23, 0.00, 0.00),
    (0.37, 0.37, 0.00, 0.21, 0.00, 0.00),
    (0.00, 0.34, 0.00, 0.00, 0.00, 0.00),
    (0.00, 0.31, 0.00, 0.00, 0.00, 0.00),
    (0.00, 0.28, 0.00, 0.00, 0.00, 0.00),
]
_CM = {"bueno": (1.00, 1.00), "regular": (0.95, 1.00), "malo": (0.90, 0.90)}


def hm(h_cm: float) -> float:
    if h_cm <= 25:
        return 1.0
    if h_cm > 63:
        return 0.0
    return 25.0 / h_cm


def vm(v_cm: float) -> float:
    if v_cm < 0 or v_cm > 175:
        return 0.0
    return 1.0 - 0.003 * abs(v_cm - 75.0)


def dm(d_cm: float) -> float:
    if d_cm <= 25:
        return 1.0
    if d_cm > 175:
        return 0.0
    return 0.82 + 4.5 / d_cm


def am(a_grados: float) -> float:
    if a_grados > 135:
        return 0.0
    return 1.0 - 0.0032 * a_grados


def fm(frecuencia: float, duracion_h: float, v_cm: float) -> float:
    """Interpolación lineal en la tabla de frecuencia; F<0.2 se toma como 0.2."""
    if duracion_h <= 1:
        col = 0
    elif duracion_h <= 2:
        col = 2
    else:
        col = 4
    if v_cm >= 75:
        col += 1
    f = max(frecuencia, 0.2)
    if f > 15:
        return 0.0
    i = bisect_left(_F, f)
    if _F[i] == f:
        return _FM[i][col]
    f0, f1 = _F[i - 1], _F[i]
    y0, y1 = _FM[i - 1][col], _FM[i][col]
    if y1 == 0.0:      # no se interpola hacia una celda prohibida
        return 0.0
    return y0 + (y1 - y0) * (f - f0) / (f1 - f0)


def cm(agarre: str, v_cm: float) -> float:
    agarre = agarre.lower()
    if agarre not in _CM:
        raise ValueError("Agarre debe ser bueno, regular o malo")
    return _CM[agarre][0 if v_cm < 75 else 1]


@dataclass
class ResultadoNIOSH:
    HM: float
    VM: float
    DM: float
    AM: float
    FM: float
    CM: float
    RWL: float
    LI: float
    nivel: str

    def a_dict(self):
        return {k: round(v, 4) if isinstance(v, float) else v for k, v in asdict(self).items()}


def calcular(L: float, H: float, V: float, D: float, A: float,
             F: float, duracion_h: float, agarre: str) -> ResultadoNIOSH:
    if L <= 0:
        raise ValueError("La masa L debe ser positiva")
    m = dict(HM=hm(H), VM=vm(V), DM=dm(D), AM=am(A), FM=fm(F, duracion_h, V), CM=cm(agarre, V))
    rwl = LC
    for val in m.values():
        rwl *= val
    li = float("inf") if rwl == 0 else L / rwl
    if li <= 1.0:
        nivel = "Aceptable (LI <= 1)"
    elif li <= 3.0:
        nivel = "Riesgo moderado (1 < LI <= 3)"
    else:
        nivel = "Riesgo elevado (LI > 3)"
    return ResultadoNIOSH(RWL=rwl, LI=li, nivel=nivel, **m)
