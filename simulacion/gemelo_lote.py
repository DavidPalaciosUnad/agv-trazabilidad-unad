"""Ensayo de validación del sistema integrado en el gemelo digital (entorno relevante simulado).

Escenario: una jornada simulada de operación con 40 órdenes de transporte
entre estaciones aleatorias (semilla fija), masas entre 5 y 50 kg, intrusiones
aleatorias de personas en la trayectoria y una parada de emergencia con su
rearme manual. Se registran los indicadores del módulo de gestión, la
integridad de la cadena de trazabilidad y una prueba de manipulación.
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from gestion.config import ConfigApp  # noqa: E402
from gestion.servicio import SistemaGestion  # noqa: E402

SALIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resultados")
SEMILLA = 2026
N_ORDENES = 40


def ejecutar(semilla=SEMILLA, n=N_ORDENES):
    rng = random.Random(semilla)
    s = SistemaGestion(ConfigApp(db_path=":memory:"), semilla=semilla)
    estaciones = ["B", "E1", "E2", "E3", "D"]
    creadas = 0
    t_proxima = 0.0
    intrusiones = 0
    emergencia_hecha = False
    t_max = 4 * 3600
    while s.t_sim < t_max:
        if creadas < n and s.t_sim >= t_proxima:
            o, d = rng.sample(estaciones, 2)
            s.crear_orden({"origen": o, "destino": d, "masa_kg": round(rng.uniform(5, 50), 1),
                           "solicitante": f"OP-0{rng.randint(1, 3)}", "prioridad": rng.choice([1, 2, 2, 3])})
            creadas += 1
            t_proxima = s.t_sim + rng.uniform(20, 90)
        lg = s.agvs["AGV-01"].logica
        if lg.estado.value == "EN_RUTA" and rng.random() < 0.004:
            s.simular_obstaculo("AGV-01", round(rng.uniform(0.6, 2.5), 2), round(rng.uniform(1.5, 6.0), 1))
            intrusiones += 1
        if not emergencia_hecha and creadas >= n // 2 and lg.estado.value == "EN_RUTA":
            s.emergencia("AGV-01")
            s.avanzar(5.0)
            s.rearmar("AGV-01")
            emergencia_hecha = True
        s.avanzar(1.0)
        ind = s.indicadores()
        if creadas == n and ind["ordenes"]["PENDIENTE"] + ind["ordenes"]["ASIGNADA"] + ind["ordenes"]["EN_CURSO"] == 0:
            break
    ind = s.indicadores()
    verif = s.verificar_trazabilidad()
    # Prueba de manipulación: se altera la masa registrada en un evento intermedio
    ev = s.db.todos("SELECT id, detalle FROM eventos WHERE tipo='ORDEN_CREADA' ORDER BY id LIMIT 1 OFFSET 5")[0]
    s.db.ejecutar("UPDATE eventos SET detalle=? WHERE id=?", (ev["detalle"].replace('"masa_kg":', '"masa_kg":1'), ev["id"]))
    verif_alterada = s.verificar_trazabilidad()
    bat = s.agvs["AGV-01"].logica.bateria
    return {
        "semilla": semilla, "ordenes_creadas": creadas, "duracion_simulada_s": round(s.t_sim, 1),
        "intrusiones_simuladas": intrusiones, "indicadores": ind,
        "trazabilidad": verif, "prueba_manipulacion": verif_alterada,
        "bateria_final_pct": round(bat, 1),
        "distancia_total_agv_m": round(s.agvs["AGV-01"].logica.distancia_recorrida, 1),
    }


if __name__ == "__main__":
    os.makedirs(SALIDA, exist_ok=True)
    r = ejecutar()
    with open(os.path.join(SALIDA, "gemelo_lote.json"), "w", encoding="utf-8") as f:
        json.dump(r, f, indent=2, ensure_ascii=False)
    print(json.dumps(r, indent=2, ensure_ascii=False))
