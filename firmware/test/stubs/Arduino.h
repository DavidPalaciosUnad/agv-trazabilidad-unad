// Stub mínimo de la API de Arduino-ESP32 para verificar la compilación del
// sketch en el PC (no reemplaza la compilación con el núcleo real en Wokwi).
#pragma once
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdarg.h>
#ifndef ESP_ARDUINO_VERSION_MAJOR
#define ESP_ARDUINO_VERSION_MAJOR 3
#endif
typedef uint8_t byte;
#define HIGH 1
#define LOW 0
#define INPUT 0
#define OUTPUT 1
#define INPUT_PULLUP 2
template <class T> T constrain(T x, T a, T b) { return x < a ? a : (x > b ? b : x); }
inline void pinMode(int, int) {}
inline void digitalWrite(int, int) {}
inline int digitalRead(int) { return HIGH; }
inline void delayMicroseconds(unsigned) {}
inline unsigned long pulseIn(int, int, unsigned long) { return 0; }
inline int analogRead(int) { return 2048; }
inline void analogReadResolution(int) {}
inline unsigned long millis() { return 0; }
inline uint32_t esp_random() { return 0x1234; }
#if ESP_ARDUINO_VERSION_MAJOR >= 3
inline bool ledcAttachChannel(int, int, int, int) { return true; }
inline void ledcWrite(int, int) {}
#else
inline void ledcSetup(int, int, int) {}
inline void ledcAttachPin(int, int) {}
inline void ledcWrite(int, int) {}
#endif
struct SerialStub {
  void begin(long) {}
  void println(const char*) {}
  int printf(const char* f, ...) { va_list a; va_start(a, f); int n = vprintf(f, a); va_end(a); return n; }
};
static SerialStub Serial;
