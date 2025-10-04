// Simple LM75B driver for OpenEVSE
#pragma once
#include "Arduino.h"
#include "./Wire.h"
#include "i2caddr.h"

class LM75B {
  int8_t _present;
  uint8_t _addr;
  int16_t read16(uint8_t reg);
public:
  LM75B(uint8_t addr = LM75B_ADDRESS) : _present(0), _addr(addr) {}
  int8_t begin();
  // returns temperature in 0.1 degrees C (same convention as MCP9808 readAmbient())
  int16_t readTempC10();
};
