"""Pruebas de la ecuación revisada de NIOSH (Waters et al., 1993; 1994)."""
import math

import pytest

from gestion import niosh


def test_condiciones_ideales_rwl_igual_constante_de_carga():
    r = niosh.calcular(L=23, H=25, V=75, D=25, A=0, F=0.2, duracion_h=1, agarre="bueno")
    assert r.RWL == pytest.approx(23.0)
    assert r.LI == pytest.approx(1.0)


def test_multiplicadores_individuales():
    assert niosh.hm(50) == pytest.approx(0.5)
    assert niosh.vm(0) == pytest.approx(0.775)
    assert niosh.dm(100) == pytest.approx(0.865)
    assert niosh.am(90) == pytest.approx(0.712)
    assert niosh.hm(70) == 0.0 and niosh.am(140) == 0.0 and niosh.vm(180) == 0.0


def test_tabla_frecuencia_y_agarre():
    assert niosh.fm(1, 8, 30) == pytest.approx(0.75)
    assert niosh.fm(4, 8, 30) == pytest.approx(0.45)
    assert niosh.fm(9, 8, 30) == 0.0          # celda prohibida
    assert niosh.fm(9, 8, 80) == pytest.approx(0.15)
    assert niosh.fm(0.1, 1, 30) == pytest.approx(1.0)  # F < 0,2 se toma como 0,2
    assert niosh.fm(1.5, 8, 30) == pytest.approx(0.70)  # interpolación lineal
    assert niosh.cm("regular", 30) == pytest.approx(0.95)
    assert niosh.cm("regular", 80) == pytest.approx(1.0)


def test_caso_compuesto():
    r = niosh.calcular(L=15, H=40, V=30, D=60, A=30, F=2, duracion_h=8, agarre="regular")
    esperado = 23 * (25 / 40) * (1 - 0.003 * 45) * (0.82 + 4.5 / 60) * (1 - 0.0032 * 30) * 0.65 * 0.95
    assert r.RWL == pytest.approx(esperado)
    assert r.LI == pytest.approx(15 / esperado)
    assert r.LI == pytest.approx(2.4146, abs=1e-3) and r.nivel.startswith("Riesgo moderado")


def test_entradas_invalidas():
    with pytest.raises(ValueError):
        niosh.calcular(L=0, H=25, V=75, D=25, A=0, F=1, duracion_h=1, agarre="bueno")
    with pytest.raises(ValueError):
        niosh.cm("excelente", 50)
    r = niosh.calcular(L=10, H=80, V=75, D=25, A=0, F=1, duracion_h=1, agarre="bueno")
    assert math.isinf(r.LI)
