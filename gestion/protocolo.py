"""Protocolo de mensajes entre el módulo de gestión y el AGV.

Se usa un formato de texto compacto para los comandos (servidor -> AGV),
fácil de interpretar en el microcontrolador sin bibliotecas JSON, y JSON
para la telemetría y los eventos (AGV -> servidor).

Comandos:
  ORD|<id>|<nodo0>|<n1>:<d1>;<n2>:<d2>;...|<k_carga>|<k_descarga>
  CAN|<id>
  PING|<marca_de_tiempo>
Tópicos MQTT (prefijo configurable):
  <prefijo>/<agv>/cmd        servidor -> AGV
  <prefijo>/<agv>/telemetria AGV -> servidor (1 Hz)
  <prefijo>/<agv>/evento     AGV -> servidor (por transición)
"""
import json
import re
from dataclasses import dataclass
from typing import List, Tuple

MAX_SEGMENTOS = 16
_NODO = re.compile(r"^[A-Z0-9]{1,4}$")


@dataclass
class Orden:
    id: int
    nodo0: str
    segmentos: List[Tuple[str, float]]
    k_carga: int
    k_descarga: int


def codificar_orden(o: Orden) -> str:
    segs = ";".join(f"{n}:{d:.2f}" for n, d in o.segmentos)
    return f"ORD|{o.id}|{o.nodo0}|{segs}|{o.k_carga}|{o.k_descarga}"


def decodificar_orden(msg: str) -> Orden:
    partes = msg.strip().split("|")
    if len(partes) != 6 or partes[0] != "ORD":
        raise ValueError("Formato de orden inválido")
    oid = int(partes[1])
    nodo0 = partes[2]
    if not _NODO.match(nodo0):
        raise ValueError("Nodo inicial inválido")
    segmentos = []
    for item in partes[3].split(";"):
        n, d = item.split(":")
        if not _NODO.match(n):
            raise ValueError("Nodo inválido")
        dist = float(d)
        if not (0.0 < dist < 1000.0):
            raise ValueError("Distancia fuera de rango")
        segmentos.append((n, dist))
    if not 1 <= len(segmentos) <= MAX_SEGMENTOS:
        raise ValueError("Número de segmentos fuera de rango")
    k_c, k_d = int(partes[4]), int(partes[5])
    if not (0 <= k_c <= k_d <= len(segmentos)):
        raise ValueError("Índices de carga/descarga inválidos")
    return Orden(oid, nodo0, segmentos, k_c, k_d)


def codificar_cancelacion(oid: int) -> str:
    return f"CAN|{oid}"


def codificar_ping(ts: float) -> str:
    return f"PING|{int(ts)}"


def telemetria_json(t: dict) -> str:
    return json.dumps(t, separators=(",", ":"))


def leer_json(payload) -> dict:
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8", errors="replace")
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("Se esperaba un objeto JSON")
    return data
