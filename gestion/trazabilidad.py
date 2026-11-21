"""Registro de eventos encadenado con SHA-256 (evidencia a prueba de alteraciones).

Cada evento almacena el hash del evento anterior. Si cualquier registro se
modifica o elimina, la verificación de la cadena falla a partir de ese punto.
h_i = SHA256( h_{i-1} || ts_i || tipo_i || orden_i || agv_i || detalle_i )
"""
import hashlib
import json

GENESIS = "0" * 64


def calcular_hash(hash_prev: str, ts: str, tipo: str, orden_id, agv_id, detalle: dict) -> str:
    contenido = "|".join([
        hash_prev, ts, tipo, "" if orden_id is None else str(orden_id),
        agv_id or "", json.dumps(detalle, sort_keys=True, ensure_ascii=False, separators=(",", ":")),
    ])
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()


def verificar_cadena(eventos) -> dict:
    """eventos: iterable de dicts ordenados por id con claves del esquema."""
    previo = GENESIS
    n = 0
    for ev in eventos:
        detalle = json.loads(ev["detalle"]) if isinstance(ev["detalle"], str) else ev["detalle"]
        esperado = calcular_hash(previo, ev["ts"], ev["tipo"], ev["orden_id"], ev["agv_id"], detalle)
        if ev["hash_prev"] != previo or ev["hash"] != esperado:
            return {"integra": False, "eventos_verificados": n, "falla_en_evento": ev["id"]}
        previo = ev["hash"]
        n += 1
    return {"integra": True, "eventos_verificados": n, "ultimo_hash": previo}
