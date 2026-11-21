// Núcleo portable del controlador del AGV (sin dependencias de Arduino).
// Se compila en el ESP32 (sketch.ino) y en el PC para las pruebas unitarias
// (firmware/test). La lógica replica gestion/agv.py del módulo de gestión.
#pragma once
#include <stdint.h>
#include <stddef.h>

namespace agv {

enum class Estado : uint8_t { REPOSO, EN_RUTA, EN_ESTACION, DETENIDO_OBSTACULO, PARADA_EMERGENCIA };
enum class Zona : uint8_t { LIBRE, ADVERTENCIA, PROTECCION };

const char* nombreEstado(Estado e);
const char* nombreZona(Zona z);

struct Parametros {
  float v_nominal = 0.50f;        // m/s
  float v_reducida = 0.20f;       // m/s
  float a_aceleracion = 0.50f;    // m/s^2
  float a_frenado = 1.00f;        // m/s^2, frenado de servicio
  float a_emergencia = 2.00f;     // m/s^2, parada de emergencia
  float d_advertencia = 1.20f;    // m
  float d_proteccion = 0.50f;     // m
  float t_reanudar = 2.0f;        // s
  float t_estacion = 4.0f;        // s
  float bateria_min_orden = 15.0f;// %
  float consumo_por_metro = 0.05f;// %/m
  float t_watchdog_com = 10.0f;   // s
  float trocha = 0.40f;           // m, separación entre ruedas
  float kp = 2.0f, ki = 0.0f, kd = 0.08f;  // PID de seguimiento de línea (sintonía: simulacion/seguimiento_linea.py)
};

static const int MAX_SEG = 16;

struct Segmento { char nodo[5]; float longitud; };

struct Orden {
  int32_t id = 0;
  char nodo0[5] = {0};
  Segmento seg[MAX_SEG];
  int n = 0;
  int k_carga = 0;
  int k_descarga = 0;
};

// Interpreta "ORD|id|nodo0|n1:d1;n2:d2|k_carga|k_descarga". Devuelve false si es inválido.
bool parsearOrden(const char* msg, Orden& out);

struct Entradas {
  float distancia_obst = 4.0f;  // m (HC-SR04)
  float error_linea = 0.0f;     // [-1, 1] posición normalizada de la cinta
  bool  emergencia = false;     // pulsador NC presionado (nivel activo)
  bool  rearme = false;         // pulsador de rearme
};

struct Salidas {
  float v = 0.0f;            // m/s longitudinal
  float w = 0.0f;            // rad/s
  float v_izq = 0.0f, v_der = 0.0f;  // m/s por rueda
  bool led_verde = false, led_amarillo = false, led_rojo = false, zumbador = false;
};

struct Evento { char tipo[24]; int32_t orden; char nodo[5]; };

class Controlador {
 public:
  explicit Controlador(const char* nodo_inicial, Parametros p = Parametros());
  bool recibirOrden(const Orden& o);
  bool cancelar(int32_t id);
  void latido();
  void emergencia();
  bool rearmar();
  Salidas paso(const Entradas& in, float dt);

  // Cola de eventos para publicar por MQTT
  bool sacarEvento(Evento& ev);

  Estado estado() const { return estado_; }
  Zona zona() const { return zona_; }
  const char* nodo() const { return nodo_; }
  const char* siguiente() const;
  int32_t ordenId() const { return tiene_orden_ ? orden_.id : 0; }
  float s() const { return s_; }
  float v() const { return v_; }
  float bateria() const { return bateria_; }
  void fijarBateria(float b) { bateria_ = b; }
  bool modoSeguroCom() const { return modo_seguro_com_; }

 private:
  Zona zonaPorDistancia(float d) const;
  float velocidadObjetivo() const;
  float distanciaAParada() const;
  void llegarNodo();
  void entrarEstacion(bool carga);
  void salirEstacion();
  void cambiar(Estado e);
  void emitir(const char* tipo);

  Parametros p_;
  Estado estado_ = Estado::REPOSO;
  Estado previo_emergencia_ = Estado::REPOSO;
  Zona zona_ = Zona::LIBRE;
  char nodo_[5];
  Orden orden_;
  bool tiene_orden_ = false;
  bool estacion_carga_ = true;
  int k_ = 0;
  float s_ = 0.0f, v_ = 0.0f, bateria_ = 100.0f;
  float t_despejado_ = 0.0f, t_estacion_ = 0.0f, t_sin_latido_ = 0.0f;
  bool modo_seguro_com_ = false;
  // PID
  float integ_ = 0.0f, err_prev_ = 0.0f;
  // Cola circular de eventos
  Evento cola_[12];
  int cab_ = 0, n_ev_ = 0;
};

}  // namespace agv
