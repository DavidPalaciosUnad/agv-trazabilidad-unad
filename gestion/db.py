"""Persistencia en SQLite (consultas parametrizadas en todo el módulo)."""
import sqlite3
import threading

ESQUEMA = """
CREATE TABLE IF NOT EXISTS ordenes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo        TEXT UNIQUE NOT NULL,
    origen        TEXT NOT NULL,
    destino       TEXT NOT NULL,
    masa_kg       REAL NOT NULL CHECK (masa_kg > 0),
    descripcion   TEXT,
    solicitante   TEXT NOT NULL,          -- código de rol, nunca nombre (Ley 1581 de 2012)
    prioridad     INTEGER NOT NULL DEFAULT 2 CHECK (prioridad BETWEEN 1 AND 3),
    estado        TEXT NOT NULL DEFAULT 'PENDIENTE',
    agv_id        TEXT,
    distancia_m   REAL,
    creada        TEXT NOT NULL,
    asignada      TEXT,
    iniciada      TEXT,
    completada    TEXT
);
CREATE TABLE IF NOT EXISTS eventos (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT NOT NULL,
    tipo      TEXT NOT NULL,
    orden_id  INTEGER,
    agv_id    TEXT,
    detalle   TEXT NOT NULL,
    hash_prev TEXT NOT NULL,
    hash      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS telemetria (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    agv_id  TEXT NOT NULL,
    estado  TEXT NOT NULL,
    zona    TEXT,
    nodo    TEXT,
    x       REAL, y REAL, v REAL, d_obst REAL, bateria REAL
);
CREATE TABLE IF NOT EXISTS evaluaciones_niosh (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT NOT NULL,
    tarea     TEXT NOT NULL,
    momento   TEXT NOT NULL CHECK (momento IN ('LINEA_BASE','POSINTERVENCION')),
    L REAL, H REAL, V REAL, D REAL, A REAL, F REAL, duracion_h REAL, agarre TEXT,
    RWL REAL, LI REAL
);
CREATE INDEX IF NOT EXISTS ix_eventos_orden ON eventos(orden_id);
CREATE INDEX IF NOT EXISTS ix_ordenes_estado ON ordenes(estado);
"""


class BaseDatos:
    def __init__(self, ruta: str):
        self.con = sqlite3.connect(ruta, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.executescript(ESQUEMA)
        self.lock = threading.RLock()

    def ejecutar(self, sql: str, params=()):
        with self.lock:
            cur = self.con.execute(sql, params)
            self.con.commit()
            return cur

    def uno(self, sql: str, params=()):
        with self.lock:
            fila = self.con.execute(sql, params).fetchone()
            return dict(fila) if fila else None

    def todos(self, sql: str, params=()):
        with self.lock:
            return [dict(f) for f in self.con.execute(sql, params).fetchall()]
