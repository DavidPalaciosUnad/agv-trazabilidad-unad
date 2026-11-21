"""Modelo geométrico de la planta (gemelo digital) y cálculo de rutas.

La guía del piso se representa como un grafo no dirigido cuyos nodos son
las estaciones y cuyas aristas son los tramos de cinta. La ruta más corta se
obtiene con el algoritmo de Dijkstra.
"""
import heapq
import math
from typing import Dict, List, Tuple

from .config import ARISTAS, ESTACIONES


class Planta:
    def __init__(self, estaciones: Dict = None, aristas: List[Tuple[str, str]] = None):
        self.estaciones = dict(estaciones or ESTACIONES)
        self.adyacencia: Dict[str, Dict[str, float]] = {k: {} for k in self.estaciones}
        for a, b in (aristas or ARISTAS):
            if a not in self.estaciones or b not in self.estaciones:
                raise ValueError(f"Arista con estación inexistente: {a}-{b}")
            d = self.distancia_euclidiana(a, b)
            self.adyacencia[a][b] = d
            self.adyacencia[b][a] = d

    def distancia_euclidiana(self, a: str, b: str) -> float:
        ea, eb = self.estaciones[a], self.estaciones[b]
        return math.hypot(eb["x"] - ea["x"], eb["y"] - ea["y"])

    def ruta_mas_corta(self, origen: str, destino: str) -> Tuple[List[str], float]:
        """Dijkstra. Devuelve (lista de nodos, distancia total en m)."""
        if origen not in self.estaciones or destino not in self.estaciones:
            raise KeyError("Estación inexistente")
        if origen == destino:
            return [origen], 0.0
        dist = {origen: 0.0}
        previo = {}
        cola = [(0.0, origen)]
        visitados = set()
        while cola:
            d, u = heapq.heappop(cola)
            if u in visitados:
                continue
            visitados.add(u)
            if u == destino:
                break
            for v, w in self.adyacencia[u].items():
                nd = d + w
                if nd < dist.get(v, math.inf):
                    dist[v] = nd
                    previo[v] = u
                    heapq.heappush(cola, (nd, v))
        if destino not in dist:
            raise ValueError(f"No hay ruta entre {origen} y {destino}")
        camino = [destino]
        while camino[-1] != origen:
            camino.append(previo[camino[-1]])
        camino.reverse()
        return camino, dist[destino]

    def plan_orden(self, nodo_agv: str, origen: str, destino: str):
        """Ruta completa AGV -> origen (carga) -> destino (descarga).

        Devuelve (nodo_inicial, segmentos[(nodo, longitud)], k_carga, k_descarga)
        donde k_* son índices 1-based dentro de segmentos (0 = nodo inicial).
        """
        tramo1, _ = self.ruta_mas_corta(nodo_agv, origen)
        tramo2, _ = self.ruta_mas_corta(origen, destino)
        nodos = tramo1 + tramo2[1:]
        segmentos = []
        for a, b in zip(nodos[:-1], nodos[1:]):
            segmentos.append((b, round(self.adyacencia[a][b], 3)))
        k_carga = len(tramo1) - 1
        k_descarga = len(nodos) - 1
        return nodos[0], segmentos, k_carga, k_descarga

    def posicion(self, a: str, b: str, s: float) -> Tuple[float, float]:
        """Coordenadas (x, y) a s metros de 'a' sobre el tramo a->b."""
        ea, eb = self.estaciones[a], self.estaciones[b]
        if b not in self.adyacencia[a]:
            return ea["x"], ea["y"]   # telemetría transitoria (p. ej. AGV remoto aún no sincronizado)
        L = self.adyacencia[a][b]
        f = 0.0 if L == 0 else max(0.0, min(1.0, s / L))
        return ea["x"] + f * (eb["x"] - ea["x"]), ea["y"] + f * (eb["y"] - ea["y"])

    def a_dict(self):
        return {
            "estaciones": [{"id": k, **v} for k, v in self.estaciones.items()],
            "aristas": [{"a": a, "b": b, "longitud": round(w, 3)}
                        for a, vec in self.adyacencia.items() for b, w in vec.items() if a < b],
        }
