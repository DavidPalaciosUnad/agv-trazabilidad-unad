// Firmware del AGV de bajo costo — ESP32-DevKitC V4
// Proyecto de grado: prototipo de AGV con trazabilidad de órdenes de transporte.
//
// Funciones: lazo de control a 50 Hz (núcleo agv_core), lectura del sensor
// ultrasónico frontal, seguimiento de línea, parada de emergencia con rearme
// manual, señalización luminosa y sonora, pantalla LCD 20x4 y comunicación
// MQTT con el módulo de gestión (comandos, telemetría a 1 Hz y eventos).
//
// En Wokwi: el potenciómetro emula el arreglo de sensores de línea (error
// lateral normalizado), los LED "MOTOR IZQ/DER" muestran el PWM de cada rueda
// y el control deslizante del HC-SR04 permite simular personas u obstáculos.
#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include "agv_core.h"

// Compatibilidad entre núcleos ESP32 Arduino 2.x y 3.x para el PWM (LEDC)
#ifndef ESP_ARDUINO_VERSION_MAJOR
#define ESP_ARDUINO_VERSION_MAJOR 2
#endif
void pwmIniciar(int pin, int canal) {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttachChannel(pin, 1000, 10, canal);
#else
  ledcSetup(canal, 1000, 10);
  ledcAttachPin(pin, canal);
#endif
}
void pwmEscribir(int pin, int canal, int duty) {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  (void)canal;
  ledcWrite(pin, duty);
#else
  (void)pin;
  ledcWrite(canal, duty);
#endif
}

// ------------------------------- Configuración -----------------------------
const char* WIFI_SSID = "Wokwi-GUEST";      // en el montaje físico: red del taller
const char* WIFI_PASS = "";
const char* MQTT_HOST = "broker.hivemq.com";  // broker público de pruebas
const uint16_t MQTT_PORT = 1883;
const char* AGV_ID = "AGV-01";
const char* PREFIJO = "unad/agv-pg";          // debe coincidir con AGV_MQTT_PREFIJO
const char* NODO_INICIAL = "H";

// ------------------------------- Pines --------------------------------------
const int PIN_TRIG = 5;          // HC-SR04 TRIG
const int PIN_ECHO = 18;         // HC-SR04 ECHO (divisor 5 V -> 3,3 V en físico)
const int PIN_LINEA = 34;        // ADC1_CH6: arreglo de línea (potenciómetro en Wokwi)
const int PIN_EMERGENCIA = 27;   // seta de emergencia (contacto a GND, INPUT_PULLUP)
const int PIN_REARME = 26;       // pulsador de rearme
const int PIN_LED_VERDE = 25;
const int PIN_LED_AMARILLO = 33;
const int PIN_LED_ROJO = 32;
const int PIN_ZUMBADOR = 19;
const int PIN_PWM_IZQ = 16;      // al driver del motor izquierdo
const int PIN_PWM_DER = 17;      // al driver del motor derecho
const float V_RUEDA_MAX = 0.80f; // m/s a PWM 100 %

LiquidCrystal_I2C lcd(0x27, 20, 4);
WiFiClient red;
PubSubClient mqtt(red);
agv::Controlador ctrl(NODO_INICIAL);

char topicoCmd[48], topicoTel[48], topicoEv[48];
unsigned long tControl = 0, tTelemetria = 0, tLcd = 0, tSensor = 0, tReconexion = 0;
float distanciaFiltrada = 4.0f;

// ------------------------------- Sensores -----------------------------------
float leerDistancia() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  unsigned long us = pulseIn(PIN_ECHO, HIGH, 25000UL);   // máx. ~4 m
  if (us == 0) return 4.0f;
  return (us * 0.000343f) / 2.0f;                        // m
}

float leerErrorLinea() {
  int crudo = analogRead(PIN_LINEA);                     // 0..4095
  return (crudo - 2047.5f) / 2047.5f;                    // [-1, 1]
}

// ------------------------------- MQTT ---------------------------------------
void publicarEvento(const agv::Evento& ev) {
  char buf[160];
  snprintf(buf, sizeof buf, "{\"ev\":\"%s\",\"orden\":%ld,\"nodo\":\"%s\",\"agv\":\"%s\"}",
           ev.tipo, (long)ev.orden, ev.nodo, AGV_ID);
  mqtt.publish(topicoEv, buf);
}

void publicarTelemetria() {
  char buf[220];
  char ord[12];
  if (ctrl.ordenId()) snprintf(ord, sizeof ord, "%ld", (long)ctrl.ordenId());
  else snprintf(ord, sizeof ord, "null");
  snprintf(buf, sizeof buf,
           "{\"agv\":\"%s\",\"st\":\"%s\",\"zona\":\"%s\",\"ord\":%s,\"nodo\":\"%s\",\"sig\":\"%s\","
           "\"s\":%.3f,\"v\":%.3f,\"d\":%.2f,\"bat\":%.1f}",
           AGV_ID, agv::nombreEstado(ctrl.estado()), agv::nombreZona(ctrl.zona()), ord, ctrl.nodo(),
           ctrl.siguiente(), ctrl.s(), ctrl.v(), distanciaFiltrada, ctrl.bateria());
  mqtt.publish(topicoTel, buf);
}

void alRecibir(char* topico, byte* payload, unsigned int len) {
  (void)topico;                                 // un solo tópico suscrito (cmd)
  char msg[200];
  if (len >= sizeof msg) return;                 // descarta mensajes sobredimensionados
  memcpy(msg, payload, len);
  msg[len] = '\0';
  if (strncmp(msg, "ORD|", 4) == 0) {
    agv::Orden o;
    if (agv::parsearOrden(msg, o)) ctrl.recibirOrden(o);
  } else if (strncmp(msg, "CAN|", 4) == 0) {
    ctrl.cancelar(atol(msg + 4));
  } else if (strncmp(msg, "PING|", 5) == 0) {
    ctrl.latido();
  } else if (strncmp(msg, "EST|", 4) == 0) {
    ctrl.emergencia();                          // parada remota desde el módulo de gestión
  } else if (strncmp(msg, "RST|", 4) == 0) {
    if (digitalRead(PIN_EMERGENCIA) == HIGH) ctrl.rearmar();  // solo con la seta liberada
  }
}

void asegurarConexion() {
  if (WiFi.status() != WL_CONNECTED || mqtt.connected()) return;
  if (millis() - tReconexion < 3000) return;    // reintento no bloqueante
  tReconexion = millis();
  char id[32];
  snprintf(id, sizeof id, "agv-%s-%04X", AGV_ID, (unsigned)(esp_random() & 0xFFFF));
  if (mqtt.connect(id)) mqtt.subscribe(topicoCmd, 1);
}

// ------------------------------- Pantalla -----------------------------------
void actualizarLcd() {
  char l[21];
  lcd.setCursor(0, 0);
  snprintf(l, sizeof l, "%-20s", agv::nombreEstado(ctrl.estado()));
  lcd.print(l);
  lcd.setCursor(0, 1);
  snprintf(l, sizeof l, "OT:%-5ld %s->%-4s   ", (long)ctrl.ordenId(), ctrl.nodo(), ctrl.siguiente());
  lcd.print(l);
  lcd.setCursor(0, 2);
  snprintf(l, sizeof l, "v=%.2fm/s d=%.2fm  ", ctrl.v(), distanciaFiltrada);
  lcd.print(l);
  lcd.setCursor(0, 3);
  snprintf(l, sizeof l, "Bat %5.1f%% %s  ", ctrl.bateria(), mqtt.connected() ? "MQTT ok" : "sin red");
  lcd.print(l);
}

// ------------------------------- Programa -----------------------------------
void setup() {
  Serial.begin(115200);
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  pinMode(PIN_EMERGENCIA, INPUT_PULLUP);
  pinMode(PIN_REARME, INPUT_PULLUP);
  pinMode(PIN_LED_VERDE, OUTPUT);
  pinMode(PIN_LED_AMARILLO, OUTPUT);
  pinMode(PIN_LED_ROJO, OUTPUT);
  pinMode(PIN_ZUMBADOR, OUTPUT);
  pwmIniciar(PIN_PWM_IZQ, 0);                   // 1 kHz, 10 bits
  pwmIniciar(PIN_PWM_DER, 1);
  analogReadResolution(12);

  lcd.init();
  lcd.backlight();
  lcd.print("AGV bajo costo");
  lcd.setCursor(0, 1);
  lcd.print("Iniciando...");

  snprintf(topicoCmd, sizeof topicoCmd, "%s/%s/cmd", PREFIJO, AGV_ID);
  snprintf(topicoTel, sizeof topicoTel, "%s/%s/telemetria", PREFIJO, AGV_ID);
  snprintf(topicoEv, sizeof topicoEv, "%s/%s/evento", PREFIJO, AGV_ID);

  WiFi.begin(WIFI_SSID, WIFI_PASS, 6);
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(alRecibir);
  mqtt.setBufferSize(512);
  Serial.println("AGV listo. Esperando ordenes por MQTT.");
}

void loop() {
  unsigned long ahora = millis();
  asegurarConexion();
  mqtt.loop();

  if (ahora - tSensor >= 60) {                   // HC-SR04: ciclo de medición de 60 ms
    tSensor = ahora;
    float d = leerDistancia();
    distanciaFiltrada = 0.6f * d + 0.4f * distanciaFiltrada;   // filtro exponencial simple
    if (d < 0.5f) distanciaFiltrada = d;         // la detección cercana no se retarda
  }

  if (ahora - tControl >= 20) {                  // lazo de control a 50 Hz
    float dt = (ahora - tControl) / 1000.0f;
    tControl = ahora;
    agv::Entradas in;
    in.distancia_obst = distanciaFiltrada;
    in.error_linea = leerErrorLinea();
    in.emergencia = digitalRead(PIN_EMERGENCIA) == LOW;
    in.rearme = digitalRead(PIN_REARME) == LOW;
    agv::Salidas out = ctrl.paso(in, dt);

    int pwmI = (int)(constrain(out.v_izq / V_RUEDA_MAX, 0.0f, 1.0f) * 1023);
    int pwmD = (int)(constrain(out.v_der / V_RUEDA_MAX, 0.0f, 1.0f) * 1023);
    if (ctrl.estado() == agv::Estado::PARADA_EMERGENCIA) { pwmI = 0; pwmD = 0; }  // corte por software
    pwmEscribir(PIN_PWM_IZQ, 0, pwmI);
    pwmEscribir(PIN_PWM_DER, 1, pwmD);
    digitalWrite(PIN_LED_VERDE, out.led_verde);
    digitalWrite(PIN_LED_AMARILLO, out.led_amarillo);
    digitalWrite(PIN_LED_ROJO, out.led_rojo);
    digitalWrite(PIN_ZUMBADOR, out.zumbador && ((ahora / 250) % 2));

    agv::Evento ev;
    while (ctrl.sacarEvento(ev)) {
      Serial.printf("[%lu] %s orden=%ld nodo=%s\n", ahora, ev.tipo, (long)ev.orden, ev.nodo);
      if (mqtt.connected()) publicarEvento(ev);
    }
  }

  if (ahora - tTelemetria >= 1000) {
    tTelemetria = ahora;
    if (mqtt.connected()) publicarTelemetria();
  }
  if (ahora - tLcd >= 250) {
    tLcd = ahora;
    actualizarLcd();
  }
}
