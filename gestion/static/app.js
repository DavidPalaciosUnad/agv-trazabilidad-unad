"use strict";
// Interfaz del módulo de gestión: consulta el estado cada 500 ms y dibuja el gemelo digital.
const $ = (id) => document.getElementById(id);
const COLOR = { EN_RUTA: "#2E8B57", EN_ESTACION: "#2F6FB3", DETENIDO_OBSTACULO: "#E8A33D",
  PARADA_EMERGENCIA: "#C0392B", REPOSO: "#5B6770" };
let PLANTA = null;
let rastro = [];

async function api(url, opciones = {}) {
  const r = await fetch(url, { headers: { "Content-Type": "application/json" }, ...opciones });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `Error ${r.status}`);
  return data;
}

function escalar() {
  const xs = PLANTA.estaciones.map((e) => e.x), ys = PLANTA.estaciones.map((e) => e.y);
  const minx = Math.min(...xs) - 1.5, maxx = Math.max(...xs) + 1.5;
  const miny = Math.min(...ys) - 1.5, maxy = Math.max(...ys) + 1.5;
  const c = $("lienzo");
  const k = Math.min(c.width / (maxx - minx), c.height / (maxy - miny));
  const ox = (c.width - k * (maxx - minx)) / 2, oy = (c.height - k * (maxy - miny)) / 2;
  return (x, y) => [ox + (x - minx) * k, c.height - (oy + (y - miny) * k)];
}

function dibujar(agvs) {
  const c = $("lienzo"), g = c.getContext("2d");
  const P = escalar();
  g.clearRect(0, 0, c.width, c.height);
  // Cuadrícula de 1 m
  g.strokeStyle = "#E3E8EE"; g.lineWidth = 1;
  for (let x = -1; x <= 16; x++) { const [a, b] = P(x, -1), [, d] = P(x, 9); g.beginPath(); g.moveTo(a, b); g.lineTo(a, d); g.stroke(); }
  for (let y = -1; y <= 9; y++) { const [a, b] = P(-1, y), [e] = P(16, y); g.beginPath(); g.moveTo(a, b); g.lineTo(e, b); g.stroke(); }
  // Guía del piso
  const est = Object.fromEntries(PLANTA.estaciones.map((e) => [e.id, e]));
  g.strokeStyle = "#1C2833"; g.lineWidth = 6; g.lineCap = "round";
  for (const ar of PLANTA.aristas) {
    const [x1, y1] = P(est[ar.a].x, est[ar.a].y), [x2, y2] = P(est[ar.b].x, est[ar.b].y);
    g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2, y2); g.stroke();
    g.fillStyle = "#5B6770"; g.font = "12px Arial";
    g.fillText(`${ar.longitud.toFixed(1)} m`, (x1 + x2) / 2 + 6, (y1 + y2) / 2 - 6);
  }
  // Estaciones
  for (const e of PLANTA.estaciones) {
    const [x, y] = P(e.x, e.y);
    g.fillStyle = e.tipo === "base" ? "#E8A33D" : "#0B2545";
    g.fillRect(x - 16, y - 16, 32, 32);
    g.fillStyle = "#fff"; g.font = "bold 13px Arial"; g.textAlign = "center"; g.textBaseline = "middle";
    g.fillText(e.id, x, y);
    g.fillStyle = "#1C2833"; g.font = "12px Arial";
    g.fillText(e.nombre, x, y + (e.y > 4 ? -28 : 30));
  }
  g.textAlign = "left"; g.textBaseline = "alphabetic";
  // AGV, campo de advertencia y rastro
  for (const a of agvs) {
    const [x, y] = P(a.x, a.y);
    rastro.push([a.x, a.y]); if (rastro.length > 120) rastro.shift();
    g.strokeStyle = "rgba(46,139,87,.35)"; g.lineWidth = 3; g.beginPath();
    rastro.forEach(([rx, ry], i) => { const [px, py] = P(rx, ry); i ? g.lineTo(px, py) : g.moveTo(px, py); });
    g.stroke();
    const kpx = P(PLANTA.parametros.d_advertencia, 0)[0] - P(0, 0)[0];
    g.fillStyle = a.zona === "LIBRE" ? "rgba(46,139,87,.10)" : "rgba(232,163,61,.22)";
    g.beginPath(); g.arc(x, y, kpx, 0, 2 * Math.PI); g.fill();
    g.fillStyle = COLOR[a.st] || "#5B6770";
    g.beginPath(); g.arc(x, y, 13, 0, 2 * Math.PI); g.fill();
    g.strokeStyle = "#fff"; g.lineWidth = 2; g.stroke();
    g.fillStyle = "#1C2833"; g.font = "bold 12px Arial"; g.fillText(a.agv, x + 16, y - 14);
  }
}

function pintarEstado(d) {
  $("reloj").textContent = d.ts.slice(11, 19);
  $("modo").textContent = d.modo === "mqtt" ? "AGV conectado por MQTT" : "Gemelo digital (simulado)";
  const a = d.agvs[0];
  if (a) {
    $("e-estado").textContent = a.st.replaceAll("_", " ");
    $("e-estado").style.color = COLOR[a.st] || "inherit";
    $("e-zona").textContent = a.zona;
    $("e-orden").textContent = a.ord ? `#${a.ord}` : "ninguna";
    $("e-nodo").textContent = `${a.nodo} → ${a.sig || "—"}`;
    $("e-vel").textContent = `${a.v.toFixed(2)} m/s`;
    $("e-dist").textContent = a.d_obst >= 4 ? "> 4,00 m (libre)" : `${a.d_obst.toFixed(2)} m`;
    $("e-bat").textContent = `${a.bat.toFixed(1)} %`;
    $("e-bat-barra").style.width = `${a.bat}%`;
  }
  const k = d.indicadores;
  $("k-traslados").textContent = k.traslados_manuales_evitados;
  $("k-masa").textContent = k.masa_transportada_kg.toLocaleString("es-CO");
  $("k-ciclo").textContent = k.tiempo_ciclo_medio_s ?? "—";
  $("k-exito").textContent = k.tasa_exito == null ? "—" : `${(k.tasa_exito * 100).toFixed(0)} %`;
  $("k-paradas").textContent = k.paradas_por_obstaculo;
  dibujar(d.agvs);
}

const hora = (ts) => (ts ? ts.slice(11, 19) : "—");

async function refrescarTablas() {
  const ords = await api("/api/ordenes");
  $("t-ordenes").innerHTML = "";
  for (const o of ords) {
    const tr = document.createElement("tr");
    const celdas = [o.codigo, `${o.origen} → ${o.destino}`, `${o.masa_kg} kg`, null, hora(o.creada), hora(o.completada)];
    celdas.forEach((t, i) => {
      const td = document.createElement("td");
      if (i === 3) { const s = document.createElement("span"); s.className = `est ${o.estado}`; s.textContent = o.estado; td.appendChild(s); }
      else td.textContent = t;
      tr.appendChild(td);
    });
    const td = document.createElement("td");
    if (["PENDIENTE", "ASIGNADA", "EN_CURSO"].includes(o.estado)) {
      const b = document.createElement("button"); b.className = "btn"; b.textContent = "Cancelar";
      b.onclick = () => api(`/api/ordenes/${o.id}/cancelar`, { method: "POST" }).then(refrescarTablas);
      td.appendChild(b);
    }
    tr.appendChild(td);
    $("t-ordenes").appendChild(tr);
  }
  const evs = await api("/api/eventos?limite=60");
  $("t-eventos").innerHTML = "";
  for (const e of evs) {
    const tr = document.createElement("tr");
    [e.id, hora(e.ts), e.tipo, e.orden_id ?? "—", e.detalle, e.hash.slice(0, 12) + "…"].forEach((t, i) => {
      const td = document.createElement("td"); td.textContent = t;
      if (i === 4) td.className = "det"; if (i === 5) td.className = "hash";
      tr.appendChild(td);
    });
    $("t-eventos").appendChild(tr);
  }
  const v = await api("/api/trazabilidad/verificar");
  $("k-cadena").textContent = v.integra ? `✔ ${v.eventos_verificados}` : `✖ evento ${v.falla_en_evento}`;
}

function formJSON(f) { return Object.fromEntries(new FormData(f).entries()); }

async function iniciar() {
  PLANTA = await api("/api/planta");
  for (const sel of [$("s-origen"), $("s-destino")]) {
    for (const e of PLANTA.estaciones) {
      const op = document.createElement("option"); op.value = e.id; op.textContent = `${e.id} · ${e.nombre}`;
      sel.appendChild(op);
    }
  }
  $("s-origen").value = "B"; $("s-destino").value = "E2";
  $("f-orden").onsubmit = async (ev) => {
    ev.preventDefault();
    try {
      const o = await api("/api/ordenes", { method: "POST", body: JSON.stringify(formJSON(ev.target)) });
      $("msg-orden").className = "msg ok"; $("msg-orden").textContent = `Orden ${o.codigo} registrada.`;
      refrescarTablas();
    } catch (e) { $("msg-orden").className = "msg err"; $("msg-orden").textContent = e.message; }
  };
  $("f-niosh").onsubmit = async (ev) => {
    ev.preventDefault();
    try {
      const r = await api("/api/niosh", { method: "POST", body: JSON.stringify(formJSON(ev.target)) });
      $("r-niosh").innerHTML = "";
      const li = document.createElement("div"); li.className = "li"; li.textContent = `LI = ${r.LI.toFixed(2)}`;
      const det = document.createElement("div");
      det.textContent = `RWL = ${r.RWL.toFixed(2)} kg · HM ${r.HM.toFixed(2)} · VM ${r.VM.toFixed(2)} · DM ${r.DM.toFixed(2)} · AM ${r.AM.toFixed(2)} · FM ${r.FM.toFixed(2)} · CM ${r.CM.toFixed(2)}`;
      const niv = document.createElement("p"); niv.textContent = r.nivel;
      $("r-niosh").append(li, det, niv);
    } catch (e) { $("r-niosh").textContent = e.message; }
  };
  $("b-obst").onclick = () => api("/api/simulacion/obstaculo", { method: "POST", body: JSON.stringify({ agv: "AGV-01", distancia_m: 1.0, duracion_s: 4 }) });
  $("b-emg").onclick = () => api("/api/agv/AGV-01/emergencia", { method: "POST" });
  $("b-rearme").onclick = () => api("/api/agv/AGV-01/rearme", { method: "POST" });
  setInterval(async () => { try { pintarEstado(await api("/api/estado")); } catch (e) { /* reintento */ } }, 500);
  setInterval(refrescarTablas, 2000);
  refrescarTablas();
}
iniciar();
