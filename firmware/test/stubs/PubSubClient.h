#pragma once
#include "Arduino.h"
class WiFiClient;
class PubSubClient {
 public:
  explicit PubSubClient(WiFiClient&) {}
  void setServer(const char*, uint16_t) {}
  void setCallback(void (*)(char*, byte*, unsigned int)) {}
  bool setBufferSize(uint16_t) { return true; }
  bool connect(const char*) { return true; }
  bool connected() { return true; }
  bool subscribe(const char*, int) { return true; }
  bool publish(const char*, const char*) { return true; }
  bool loop() { return true; }
};
