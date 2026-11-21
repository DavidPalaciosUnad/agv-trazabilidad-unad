// Pruebas unitarias del núcleo del firmware (se ejecutan en el PC con g++).
// Compilar y ejecutar:  make -C firmware/test
#include <cmath>
#include <cstdio>
#include <cstring>
#include "../agv_esp32/agv_core.h"

using namespace agv;

static int fallas = 0, total = 0;
#define VERIFICAR(cond, desc)                                             \
  do {                                                                    \
    total++;                                                              \
    if (cond) printf("  [OK]    %s\n", desc);                             \
    else { fallas++; printf("  [FALLA] %s  (%s:%d)\n", desc, __FILE__, __LINE__); } \
  } while (0)

static Salidas avanzar(Controlador& c, float segundos, float dist = 4.0f, float err = 0.0f,
                       bool emg = false, bool rst = false) {
  Entradas in;
  in.distancia_obst = dist;
  in.error_linea = err;
  in.emergencia = emg;
  in.rearme = rst;
  Salidas o;
  int n = (int)lroundf(segundos / 0.02f);
  for (int i = 0; i < n; i++) { c.latido(); o = c.paso(in, 0.02f); }
  return o;
}

static bool hayEvento(Controlador& c, const char* tipo) {
  Evento ev;
  bool hallado = false;
  while (c.sacarEvento(ev)) if (strcmp(ev.tipo, tipo) == 0) hallado = true;
  return hallado;
}

int main() {
  printf("Pruebas del núcleo del firmware AGV\n");

  // 1. Interpretación del protocolo de órdenes
  Orden o;
  VERIFICAR(parsearOrden("ORD|7|H|B:6.00;E1:6.00;E2:6.00|1|3", o), "Orden válida se interpreta");
  VERIFICAR(o.id == 7 && o.n == 3 && o.k_carga == 1 && o.k_descarga == 3, "Campos de la orden correctos");
  VERIFICAR(std::fabs(o.seg[2].longitud - 6.0f) < 1e-4f && strcmp(o.seg[2].nodo, "E2") == 0, "Segmento 3 correcto");
  VERIFICAR(!parsearOrden("ORD|7|H|B:6.00|2|1", o), "Rechaza índices de carga/descarga incoherentes");
  VERIFICAR(!parsearOrden("ORD|x|H|B:6.00|1|1", o), "Rechaza identificador no numérico");
  VERIFICAR(!parsearOrden("ORD|7|h;|B:6.00|1|1", o), "Rechaza nodo con caracteres inválidos");
  VERIFICAR(!parsearOrden("ORD|7|H|B:-3|1|1", o), "Rechaza distancia negativa");
  VERIFICAR(!parsearOrden("XYZ|7|H|B:6|1|1", o), "Rechaza comando desconocido");

  // 2. Ciclo completo de una orden
  Controlador c("H");
  parsearOrden("ORD|1|H|B:6.00;E1:6.00;E2:6.00|1|3", o);
  VERIFICAR(c.recibirOrden(o), "Acepta orden en reposo");
  VERIFICAR(c.estado() == Estado::EN_RUTA, "Pasa a EN_RUTA");
  Salidas s = avanzar(c, 3.0f);
  VERIFICAR(std::fabs(s.v - 0.5f) < 0.01f, "Alcanza la velocidad nominal de 0,5 m/s");
  avanzar(c, 12.0f);
  VERIFICAR(c.estado() == Estado::EN_ESTACION && strcmp(c.nodo(), "B") == 0, "Se detiene en B para la carga");
  avanzar(c, 4.1f);
  VERIFICAR(c.estado() == Estado::EN_RUTA, "Reanuda tras la permanencia de carga");
  avanzar(c, 40.0f);
  VERIFICAR(c.estado() == Estado::REPOSO && strcmp(c.nodo(), "E2") == 0, "Completa la orden en E2");
  VERIFICAR(hayEvento(c, "ORDEN_COMPLETADA"), "Emite el evento ORDEN_COMPLETADA");

  // 3. Campos de advertencia y protección
  Controlador c2("H");
  parsearOrden("ORD|2|H|Z:50.00|1|1", o);
  c2.recibirOrden(o);
  avanzar(c2, 4.1f);   // tramo largo de 50 m: el AGV arranca y circula en campo libre
  avanzar(c2, 3.0f);
  s = avanzar(c2, 1.0f, 1.0f);
  VERIFICAR(c2.zona() == Zona::ADVERTENCIA && std::fabs(s.v - 0.2f) < 0.01f,
            "Campo de advertencia reduce la velocidad a 0,2 m/s");
  avanzar(c2, 0.1f, 0.40f);
  VERIFICAR(c2.estado() == Estado::DETENIDO_OBSTACULO, "Campo de protección detiene el AGV");
  avanzar(c2, 1.0f, 0.40f);
  VERIFICAR(c2.v() == 0.0f, "Velocidad nula con obstáculo presente");
  avanzar(c2, 1.0f, 4.0f);
  VERIFICAR(c2.estado() == Estado::DETENIDO_OBSTACULO, "No reanuda antes de 2 s de campo despejado");
  avanzar(c2, 1.2f, 4.0f);
  VERIFICAR(c2.estado() == Estado::EN_RUTA, "Reanuda automáticamente tras 2 s despejado");

  // 4. Parada de emergencia con rearme manual
  avanzar(c2, 2.0f, 4.0f, 0.0f, true);
  VERIFICAR(c2.estado() == Estado::PARADA_EMERGENCIA && c2.v() == 0.0f, "Emergencia detiene el vehículo");
  avanzar(c2, 1.0f, 4.0f, 0.0f, true, true);
  VERIFICAR(c2.estado() == Estado::PARADA_EMERGENCIA, "Rearme ignorado con la seta presionada");
  avanzar(c2, 3.0f);
  VERIFICAR(c2.estado() == Estado::PARADA_EMERGENCIA, "Liberar la seta no rearma por sí solo (enclavamiento)");
  avanzar(c2, 0.1f, 4.0f, 0.0f, false, true);
  VERIFICAR(c2.estado() == Estado::EN_RUTA, "Rearme manual restablece la marcha");

  // 5. Batería baja y orden en estado ocupado
  Controlador c3("H");
  c3.fijarBateria(10.0f);
  parsearOrden("ORD|3|H|B:6.00|1|1", o);
  VERIFICAR(!c3.recibirOrden(o), "Rechaza órdenes con batería < 15 %");
  Controlador c4("H");
  c4.recibirOrden(o);
  VERIFICAR(!c4.recibirOrden(o), "Rechaza una segunda orden mientras está ocupado");

  // 6. Vigilancia de comunicación (watchdog)
  Controlador c5("H");
  parsearOrden("ORD|4|H|Z:50.00|1|1", o);
  c5.recibirOrden(o);
  Entradas in;
  for (int i = 0; i < 600; i++) c5.paso(in, 0.02f);   // 12 s sin latido
  VERIFICAR(c5.modoSeguroCom(), "Activa modo seguro tras 10 s sin latido del servidor");
  VERIFICAR(c5.v() <= 0.2001f, "En modo seguro circula a velocidad reducida");

  // 7. Seguimiento de línea: signo y diferencial de velocidades
  Controlador c6("H");
  parsearOrden("ORD|5|H|Z:50.00|1|1", o);
  c6.recibirOrden(o);
  avanzar(c6, 3.0f);
  s = avanzar(c6, 0.02f, 4.0f, 0.5f);
  VERIFICAR(s.w < 0 && s.v_der < s.v_izq, "Desvío a la izquierda produce giro a la derecha");

  printf("\nResultado: %d de %d pruebas superadas\n", total - fallas, total);
  return fallas == 0 ? 0 : 1;
}
