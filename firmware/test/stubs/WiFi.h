#pragma once
#include "Arduino.h"
#define WL_CONNECTED 3
struct WiFiStub { void begin(const char*, const char*, int = 0) {} int status() { return WL_CONNECTED; } };
static WiFiStub WiFi;
class WiFiClient {};
