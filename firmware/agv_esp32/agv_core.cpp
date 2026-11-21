#include "agv_core.h"
#include <string.h>
#include <stdlib.h>
#include <math.h>

namespace agv {

const char* nombreEstado(Estado e) {
  switch (e) {
    case Estado::REPOSO: return "REPOSO";
    case Estado::EN_RUTA: return "EN_RUTA";
    case Estado::EN_ESTACION: return "EN_ESTACION";
    case Estado::DETENIDO_OBSTACULO: return "DETENIDO_OBSTACULO";
    case Estado::PARADA_EMERGENCIA: return "PARADA_EMERGENCIA";
  }
  return "?";
}

const char* nombreZona(Zona z) {
  switch (z) {
    case Zona::LIBRE: return "LIBRE";
    case Zona::ADVERTENCIA: return "ADVERTENCIA";
    case Zona::PROTECCION: return "PROTECCION";
  }
  return "?";
}

static bool nodoValido(const char* s, size_t n) {
  if (n == 0 || n > 4) return false;
  for (size_t i = 0; i < n; i++) {
    char c = s[i];
    if (!((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9'))) return false;
  }
  return true;
}

// Copia el campo [ini, fin) en dst (máx. cap-1 caracteres)
static bool copiarCampo(const char* ini, const char* fin, char* dst, size_t cap) {
  size_t n = (size_t)(fin - ini);
  if (n >= cap) return false;
  memcpy(dst, ini, n);
  dst[n] = '\0';
  return true;
}

bool parsearOrden(const char* msg, Orden& out) {
  Orden o;
  const char* campos[7];
  int nc = 0;
  campos[nc++] = msg;
  for (const char* p = msg; *p && nc < 7; p++) if (*p == '|') campos[nc++] = p + 1;
  if (nc != 6) return false;
  const char* fin_msg = msg + strlen(msg);
  auto finCampo = [&](int i) { return i + 1 < nc ? campos[i + 1] - 1 : fin_msg; };
  if (finCampo(0) - campos[0] != 3 || strncmp(campos[0], "ORD", 3) != 0) return false;
  char buf[16];
  if (!copiarCampo(campos[1], finCampo(1), buf, sizeof buf)) return false;
  char* e;
  long id = strtol(buf, &e, 10);
  if (*e != '\0' || id <= 0) return false;
  o.id = (int32_t)id;
  size_t n0 = (size_t)(finCampo(2) - campos[2]);
  if (!nodoValido(campos[2], n0)) return false;
  copiarCampo(campos[2], finCampo(2), o.nodo0, sizeof o.nodo0);
  // Segmentos "N:d;N:d"
  const char* p = campos[3];
  const char* f3 = finCampo(3);
  while (p < f3) {
    if (o.n >= MAX_SEG) return false;
    const char* sep = p;
    while (sep < f3 && *sep != ';') sep++;
    const char* dos = p;
    while (dos < sep && *dos != ':') dos++;
    if (dos == sep || !nodoValido(p, (size_t)(dos - p))) return false;
    copiarCampo(p, dos, o.seg[o.n].nodo, sizeof o.seg[o.n].nodo);
    if (!copiarCampo(dos + 1, sep, buf, sizeof buf)) return false;
    float d = strtof(buf, &e);
    if (*e != '\0' || !(d > 0.0f && d < 1000.0f)) return false;
    o.seg[o.n].longitud = d;
    o.n++;
    p = sep + 1;
  }
  if (o.n < 1) return false;
  if (!copiarCampo(campos[4], finCampo(4), buf, sizeof buf)) return false;
  o.k_carga = (int)strtol(buf, &e, 10);
  if (*e != '\0') return false;
  if (!copiarCampo(campos[5], finCampo(5), buf, sizeof buf)) return false;
  o.k_descarga = (int)strtol(buf, &e, 10);
  if (*e != '\0') return false;
  if (!(0 <= o.k_carga && o.k_carga <= o.k_descarga && o.k_descarga <= o.n)) return false;
  out = o;
  return true;
}

Controlador::Controlador(const char* nodo_inicial, Parametros p) : p_(p) {
  strncpy(nodo_, nodo_inicial, sizeof nodo_ - 1);
  nodo_[sizeof nodo_ - 1] = '\0';
}

void Controlador::emitir(const char* tipo) {
  int idx = (cab_ + n_ev_) % 12;
  if (n_ev_ == 12) { cab_ = (cab_ + 1) % 12; n_ev_--; }  // descarta el más antiguo
  strncpy(cola_[idx].tipo, tipo, sizeof cola_[idx].tipo - 1);
  cola_[idx].tipo[sizeof cola_[idx].tipo - 1] = '\0';
  cola_[idx].orden = tiene_orden_ ? orden_.id : 0;
  strncpy(cola_[idx].nodo, nodo_, sizeof cola_[idx].nodo);
  n_ev_++;
}

bool Controlador::sacarEvento(Evento& ev) {
  if (n_ev_ == 0) return false;
  ev = cola_[cab_];
  cab_ = (cab_ + 1) % 12;
  n_ev_--;
  return true;
}

void Controlador::cambiar(Estado e) {
  if (e != estado_) estado_ = e;
}

bool Controlador::recibirOrden(const Orden& o) {
  if (estado_ != Estado::REPOSO || bateria_ < p_.bateria_min_orden || strcmp(o.nodo0, nodo_) != 0) {
    emitir("ORDEN_RECHAZADA");
    return false;
  }
  orden_ = o;
  tiene_orden_ = true;
  k_ = 0;
  s_ = 0.0f;
  emitir("ORDEN_RECIBIDA");
  if (o.k_carga == 0) entrarEstacion(true);
  else cambiar(Estado::EN_RUTA);
  return true;
}

bool Controlador::cancelar(int32_t id) {
  if (!tiene_orden_ || orden_.id != id) return false;
  emitir("ORDEN_CANCELADA_AGV");
  tiene_orden_ = false;
  v_ = 0.0f;
  if (estado_ != Estado::PARADA_EMERGENCIA) cambiar(Estado::REPOSO);
  return true;
}

void Controlador::latido() {
  t_sin_latido_ = 0.0f;
  if (modo_seguro_com_) { modo_seguro_com_ = false; emitir("COMUNICACION_RESTABLECIDA"); }
}

void Controlador::emergencia() {
  if (estado_ == Estado::PARADA_EMERGENCIA) return;
  previo_emergencia_ = estado_;
  cambiar(Estado::PARADA_EMERGENCIA);
  emitir("PARADA_EMERGENCIA");
}

bool Controlador::rearmar() {
  if (estado_ != Estado::PARADA_EMERGENCIA) return false;
  emitir("REARME");
  if (!tiene_orden_) cambiar(Estado::REPOSO);
  else if (previo_emergencia_ == Estado::EN_ESTACION) cambiar(Estado::EN_ESTACION);
  else cambiar(Estado::EN_RUTA);
  return true;
}

Zona Controlador::zonaPorDistancia(float d) const {
  if (d < p_.d_proteccion) return Zona::PROTECCION;
  const float histeresis = 0.05f;  // m, evita conmutaciones por ruido del sensor
  float limite = p_.d_advertencia + (zona_ != Zona::LIBRE ? histeresis : 0.0f);
  if (d < limite) return Zona::ADVERTENCIA;
  return Zona::LIBRE;
}

float Controlador::distanciaAParada() const {
  int destino = orden_.n;
  if (orden_.k_carga > k_ && orden_.k_carga < destino) destino = orden_.k_carga;
  if (orden_.k_descarga > k_ && orden_.k_descarga < destino) destino = orden_.k_descarga;
  float d = orden_.seg[k_].longitud - s_;
  for (int j = k_ + 1; j < destino; j++) d += orden_.seg[j].longitud;
  return d;
}

float Controlador::velocidadObjetivo() const {
  if (estado_ != Estado::EN_RUTA || !tiene_orden_) return 0.0f;
  float v = p_.v_nominal;
  if (zona_ == Zona::ADVERTENCIA || modo_seguro_com_) v = p_.v_reducida;
  float restante = distanciaAParada();
  float v_aprox = sqrtf(2.0f * p_.a_frenado * (restante > 0 ? restante : 0));
  if (v_aprox < 0.05f) v_aprox = 0.05f;
  return v < v_aprox ? v : v_aprox;
}

const char* Controlador::siguiente() const {
  if (tiene_orden_ && k_ < orden_.n) return orden_.seg[k_].nodo;
  return "-";
}

void Controlador::entrarEstacion(bool carga) {
  estacion_carga_ = carga;
  t_estacion_ = 0.0f;
  cambiar(Estado::EN_ESTACION);
  emitir(carga ? "CARGA_INICIADA" : "DESCARGA_INICIADA");
}

void Controlador::salirEstacion() {
  if (!estacion_carga_) {
    emitir("DESCARGA_COMPLETADA");
    emitir("ORDEN_COMPLETADA");
    tiene_orden_ = false;
    cambiar(Estado::REPOSO);
  } else {
    emitir("CARGA_COMPLETADA");
    cambiar(Estado::EN_RUTA);
  }
}

void Controlador::llegarNodo() {
  float L = orden_.seg[k_].longitud;
  strncpy(nodo_, orden_.seg[k_].nodo, sizeof nodo_);
  int idx = k_ + 1;
  emitir("LLEGADA_NODO");
  k_ = idx;
  if (idx == orden_.k_descarga) { s_ = 0; v_ = 0; entrarEstacion(false); }
  else if (idx == orden_.k_carga) { s_ = 0; v_ = 0; entrarEstacion(true); }
  else { s_ = (s_ - L) > 0 ? (s_ - L) : 0; }
}

Salidas Controlador::paso(const Entradas& in, float dt) {
  Salidas out;
  if (in.emergencia) emergencia();                 // nivel activo: prioridad máxima
  if (in.rearme && !in.emergencia) rearmar();      // rearme solo con la seta liberada

  t_sin_latido_ += dt;
  if (t_sin_latido_ > p_.t_watchdog_com && !modo_seguro_com_ && tiene_orden_) {
    modo_seguro_com_ = true;
    emitir("FALLA_COMUNICACION");
  }
  Zona zona_previa = zona_;
  zona_ = zonaPorDistancia(in.distancia_obst);
  if (zona_ == Zona::ADVERTENCIA && zona_previa == Zona::LIBRE && estado_ == Estado::EN_RUTA && tiene_orden_)
    emitir("VELOCIDAD_REDUCIDA");

  switch (estado_) {
    case Estado::PARADA_EMERGENCIA:
      break;  // el frenado de emergencia se aplica en la dinámica longitudinal
    case Estado::EN_RUTA:
      if (zona_ == Zona::PROTECCION) {
        cambiar(Estado::DETENIDO_OBSTACULO);
        emitir("OBSTACULO_DETECTADO");
        t_despejado_ = 0.0f;
      }
      break;
    case Estado::DETENIDO_OBSTACULO:
      if (zona_ == Zona::PROTECCION) t_despejado_ = 0.0f;
      else {
        t_despejado_ += dt;
        if (t_despejado_ >= p_.t_reanudar) { emitir("OBSTACULO_DESPEJADO"); cambiar(Estado::EN_RUTA); }
      }
      break;
    case Estado::EN_ESTACION:
      t_estacion_ += dt;
      if (t_estacion_ >= p_.t_estacion) salirEstacion();
      break;
    default:
      break;
  }

  // Dinámica longitudinal con límites de aceleración y frenado
  float v_obj = velocidadObjetivo();
  float frenado = (estado_ == Estado::PARADA_EMERGENCIA) ? p_.a_emergencia : p_.a_frenado;
  if (v_ < v_obj) { v_ += p_.a_aceleracion * dt; if (v_ > v_obj) v_ = v_obj; }
  else            { v_ -= frenado * dt;           if (v_ < v_obj) v_ = v_obj; }

  // Seguimiento de línea: PID sobre el error normalizado del arreglo de sensores
  float w = 0.0f;
  if (v_ > 0.0f) {
    integ_ += in.error_linea * dt;
    if (integ_ > 0.5f) integ_ = 0.5f;
    if (integ_ < -0.5f) integ_ = -0.5f;
    float deriv = (in.error_linea - err_prev_) / dt;
    w = -(p_.kp * in.error_linea + p_.ki * integ_ + p_.kd * deriv);
  } else {
    integ_ = 0.0f;
  }
  err_prev_ = in.error_linea;

  // El vehículo sigue desplazándose mientras frena (en cualquier estado con orden)
  if (tiene_orden_ && v_ > 0.0f && k_ < orden_.n) {
    float ds = v_ * dt;
    s_ += ds;
    bateria_ -= p_.consumo_por_metro * ds;
    if (bateria_ < 0) bateria_ = 0;
    if (s_ >= orden_.seg[k_].longitud - 1e-3f) llegarNodo();
  }

  out.v = v_;
  out.w = w;
  out.v_izq = v_ - w * p_.trocha / 2.0f;
  out.v_der = v_ + w * p_.trocha / 2.0f;
  out.led_verde = (estado_ == Estado::EN_RUTA && zona_ == Zona::LIBRE);
  out.led_amarillo = (zona_ == Zona::ADVERTENCIA) || estado_ == Estado::DETENIDO_OBSTACULO || modo_seguro_com_;
  out.led_rojo = (estado_ == Estado::PARADA_EMERGENCIA);
  out.zumbador = (estado_ == Estado::DETENIDO_OBSTACULO) || (estado_ == Estado::PARADA_EMERGENCIA);
  return out;
}

}  // namespace agv
