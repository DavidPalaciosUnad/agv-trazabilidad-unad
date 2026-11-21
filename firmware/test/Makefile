# Pruebas del firmware en el PC
CXX ?= g++
CXXFLAGS = -std=c++17 -Wall -Wextra -O1
SRC = ../agv_esp32/agv_core.cpp

all: pruebas compilar_sketch

pruebas: test_core.cpp $(SRC)
	$(CXX) $(CXXFLAGS) test_core.cpp $(SRC) -o test_core
	./test_core

# Verificación sintáctica del sketch con encabezados de reemplazo (núcleo 3.x y 2.x)
compilar_sketch:
	$(CXX) $(CXXFLAGS) -fsyntax-only -I stubs -I ../agv_esp32 -include stubs/Arduino.h -x c++ ../agv_esp32/sketch.ino
	$(CXX) $(CXXFLAGS) -fsyntax-only -DESP_ARDUINO_VERSION_MAJOR=2 -I stubs -I ../agv_esp32 -include stubs/Arduino.h -x c++ ../agv_esp32/sketch.ino
	@echo "sketch.ino: compilación sintáctica correcta (núcleos 2.x y 3.x)"

clean:
	rm -f test_core
