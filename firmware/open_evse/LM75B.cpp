/*
 Simple LM75B driver
 Returns temperature in 0.1 C units (int16_t), or TEMPERATURE_NOT_INSTALLED if not present
*/
#include "open_evse.h"
#include "LM75B.h"

static inline void wiresend(uint8_t x) {
#if ARDUINO >= 100
  Wire.write((uint8_t)x);
#else
  Wire.send(x);
#endif
}

static inline uint8_t wirerecv(void) {
#if ARDUINO >= 100
  return Wire.read();
#else
  return Wire.receive();
#endif
}

int16_t LM75B::read16(uint8_t reg)
{
  int16_t val = 0;
  Wire.beginTransmission(_addr);
  wiresend(reg);
  Wire.endTransmission();

  Wire.requestFrom((uint8_t)_addr, (uint8_t)2);
  if (Wire.available() < 2) return 0;
  val = wirerecv();
  val <<= 8;
  val |= wirerecv();
  return val;
}

int8_t LM75B::begin()
{
  // Try reading temperature register to see if device responds
  Wire.beginTransmission(_addr);
  wiresend(0x00); // temp register
  if (Wire.endTransmission() != 0) {
    _present = 0;
    return 0;
  }
  // request two bytes
  Wire.requestFrom((uint8_t)_addr, (uint8_t)2);
  if (Wire.available() < 2) {
    _present = 0;
    return 0;
  }
  (void)wirerecv();
  (void)wirerecv();
  _present = 1;
  return 1;
}

int16_t LM75B::readTempC10()
{
  if (!_present) return TEMPERATURE_NOT_INSTALLED;

  int16_t raw = read16(0x00);
  // LM75B temperature format: 9-bit to 11-bit depending on variant; typical: first 9 bits = T
  // Most common LM75 family returns temp in two's complement, left-justified, MSB first.
  // We'll handle the common 11-bit format: raw >> 5 gives temperature in 0.125 C steps.

  // Use 11-bit resolution assumption: shift right 5 to get value in 0.125 C units
  int16_t traw = raw >> 5;
  // sign extend for 11-bit
  if (traw & 0x0400) traw |= 0xF800;

  // Now traw is in units of 0.125 C. Convert to 0.1 C: (traw * 125) / 10 = traw * 12.5
  // To avoid floats, multiply then divide: (traw * 125) / 10 => (traw * 25) / 2
  int32_t tmp = (int32_t)traw * 25;
  tmp /= 20; // tmp now in 0.1C

  return (int16_t)tmp;
}
