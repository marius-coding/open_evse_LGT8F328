// -*- C++ -*-
/*
 * LGT8F328P EEPROM Compatibility Layer
 *
 * The LGT8F328P has NO hardware EEPROM - it uses flash-based emulation.
 * This wrapper uses the Arduino EEPROM library from the LGT8FX core which
 * properly implements flash page swapping for EEPROM emulation.
 */

#pragma once

// Prevent avr/eeprom.h from being included since we're using Arduino EEPROM library
#define _AVR_EEPROM_H_ 1

#include <EEPROM.h>  // LGT8FX Arduino EEPROM library with flash emulation

// Wrapper functions that match AVR eeprom API but use Arduino EEPROM library
inline uint8_t lgt8f_eeprom_read_byte(const uint8_t *addr) {
  return EEPROM.read((int)(uint16_t)addr);
}

inline void lgt8f_eeprom_write_byte(uint8_t *addr, uint8_t value) {
  EEPROM.write((int)(uint16_t)addr, value);
}

inline uint16_t lgt8f_eeprom_read_word(const uint16_t *addr) {
  const uint8_t *p = (const uint8_t *)addr;
  uint8_t low = lgt8f_eeprom_read_byte(p);
  uint8_t high = lgt8f_eeprom_read_byte(p + 1);
  return (uint16_t)((high << 8) | low);
}

inline void lgt8f_eeprom_write_word(uint16_t *addr, uint16_t value) {
  uint8_t *p = (uint8_t *)addr;
  lgt8f_eeprom_write_byte(p, (uint8_t)(value & 0xFF));
  lgt8f_eeprom_write_byte(p + 1, (uint8_t)((value >> 8) & 0xFF));
}

inline uint32_t lgt8f_eeprom_read_dword(const uint32_t *addr) {
  const uint8_t *p = (const uint8_t *)addr;
  uint32_t result = 0;
  for (uint8_t i = 0; i < 4; i++) {
    result |= ((uint32_t)lgt8f_eeprom_read_byte(p + i)) << (i * 8);
  }
  return result;
}

inline void lgt8f_eeprom_write_dword(uint32_t *addr, uint32_t value) {
  uint8_t *p = (uint8_t *)addr;
  for (uint8_t i = 0; i < 4; i++) {
    lgt8f_eeprom_write_byte(p + i, (uint8_t)((value >> (i * 8)) & 0xFF));
  }
}

/* Provide the standard AVR eeprom function names that the rest of the code expects.
   These macros redirect to our LGT8F implementations which use Arduino EEPROM. */
#define eeprom_read_byte(addr)        lgt8f_eeprom_read_byte(addr)
#define eeprom_write_byte(addr, val)  lgt8f_eeprom_write_byte(addr, val)
#define eeprom_read_word(addr)        lgt8f_eeprom_read_word(addr)
#define eeprom_write_word(addr, val)  lgt8f_eeprom_write_word(addr, val)
#define eeprom_read_dword(addr)       lgt8f_eeprom_read_dword(addr)
#define eeprom_write_dword(addr, val) lgt8f_eeprom_write_dword(addr, val)
