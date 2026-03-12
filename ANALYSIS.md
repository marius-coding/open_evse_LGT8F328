# OpenEVSE LGT8F328 Firmware — Comprehensive Analysis

> **Note:** All conclusions are based solely on source code. Inferred behaviors not directly observable in code are labelled **Hypothesis**.

---

## 1. Executive Summary

OpenEVSE is an open-source Electric Vehicle Supply Equipment (EVSE) controller firmware targeting the ATmega328P (and LGT8F328P clone) microcontroller. It implements the SAE J1772 protocol for Level 1/Level 2 AC charging.

**High-level responsibilities:**

- **J1772 pilot signal generation** — produces a 1 kHz PWM pilot waveform whose duty cycle advertises the available current capacity to the EV.
- **State detection** — continuously measures the pilot line voltage to determine whether a vehicle is absent (State A), connected/ready (State B), charging (State C), or requesting ventilation (State D).
- **Safety enforcement** — GFI (Ground Fault Interrupt), ground-check, stuck-relay check, diode check, over-temperature, and over-current protection.
- **Metering** — optional ammeter and voltmeter for energy accounting.
- **Display / UI** — optional 16×2 I²C LCD with RGB or monochrome backlight and a front-panel button.
- **RAPI serial/I²C protocol** — remote API for host MCU (e.g., ESP8266/ESP32 WiFi module) to query and control the EVSE.
- **Timers & limits** — delay timer, charge-time limit, charge energy (kWh) limit, heartbeat supervision.

---

## 2. Project Map

| File | Purpose |
|---|---|
| `firmware/open_evse/open_evse.h` | Central configuration: feature `#define`s, EEPROM addresses, global declarations |
| `firmware/open_evse/open_evse.ino` | Arduino sketch entry (calls `setup()` / `loop()`) — thin wrapper |
| `firmware/open_evse/main.cpp` | Main loop, display rendering, menu system, button handling |
| `firmware/open_evse/J1772EvseController.h/.cpp` | Core EVSE state machine, relay control, safety checks |
| `firmware/open_evse/J1772Pilot.h/.cpp` | PWM pilot signal generation and ADC pilot voltage reading |
| `firmware/open_evse/Gfi.h/.cpp` | GFI (ground-fault) hardware interrupt and self-test |
| `firmware/open_evse/EnergyMeter.h/.cpp` | Watt-second / kWh accumulation and EEPROM persistence |
| `firmware/open_evse/AutoCurrentCapacityController.h/.cpp` | PP-pin auto ampacity (EmonEVSE T2) |
| `firmware/open_evse/LCD.h/.cpp` | LCD abstraction layer (LiquidTWI2 / LiquidCrystal_I2C) |
| `firmware/open_evse/rapi_proc.h/.cpp` | RAPI protocol parser, command dispatcher, transport glue |
| `firmware/open_evse/MennekesLock.h/.cpp` | Mennekes (Type 2) locking actuator driver |
| `firmware/open_evse/avrstuff.h/.cpp` | Low-level AVR helpers (ADC, digital I/O wrappers) |
| `firmware/open_evse/strings.h/.cpp` | PROGMEM string definitions |
| `firmware/open_evse/lgt8fx_eeprom.h` | LGT8F328P EEPROM compatibility shim |
| `firmware/open_evse/RTClib.h/.cpp` | DS3231 RTC driver |
| `firmware/open_evse/LM75B.h/.cpp` | LM75B temperature sensor driver |
| `firmware/open_evse/MCP9808.h/.cpp` | MCP9808 temperature sensor driver |
| `firmware/open_evse/Adafruit_TMP007.h/.cpp` | TMP007 IR temperature sensor driver |
| `firmware/open_evse/LiquidTWI2.h/.cpp` | MCP23017-based I²C LCD driver |
| `firmware/open_evse/LiquidCrystal_I2C.h/.cpp` | PCF8574-based I²C LCD driver |
| `firmware/open_evse/Wire.h/.cpp` | I²C (TWI) driver for AVR |
| `firmware/open_evse/i2caddr.h` | I²C device address definitions |
| `firmware/open_evse/Language_default.h` | English language string constants |
| `platformio.ini` | PlatformIO build matrix (US/EU/EmonEVSE variants) |
| `arduino/boards.local.txt` | Custom Arduino board definition for OpenEVSE |
| `ci/info_common.sh` | CI helper: extracts version and build info |
| `.github/workflows/build_platformio.yml` | PlatformIO CI build workflow |
| `.github/workflows/build_arduino.yml` | Arduino CLI CI build workflow |

---

## 3. Architecture & Data Flow

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 520" font-family="monospace" font-size="12">
  <!-- Main Loop -->
  <rect x="310" y="10" width="180" height="40" rx="6" fill="#4a90d9" stroke="#2c5f8a" stroke-width="1.5"/>
  <text x="400" y="35" text-anchor="middle" fill="white" font-weight="bold">Main Loop (main.cpp)</text>

  <!-- J1772EvseController -->
  <rect x="270" y="90" width="260" height="40" rx="6" fill="#357abd" stroke="#2c5f8a" stroke-width="1.5"/>
  <text x="400" y="115" text-anchor="middle" fill="white" font-weight="bold">J1772EVSEController</text>
  <text x="400" y="128" text-anchor="middle" fill="#ddd" font-size="10">(J1772EvseController.cpp)</text>

  <!-- Pilot -->
  <rect x="50" y="190" width="150" height="40" rx="6" fill="#5ba85a" stroke="#3a7039" stroke-width="1.5"/>
  <text x="125" y="210" text-anchor="middle" fill="white">J1772Pilot</text>
  <text x="125" y="223" text-anchor="middle" fill="#ddd" font-size="10">(J1772Pilot.cpp)</text>

  <!-- GFI -->
  <rect x="220" y="190" width="120" height="40" rx="6" fill="#c0392b" stroke="#922b21" stroke-width="1.5"/>
  <text x="280" y="210" text-anchor="middle" fill="white">Gfi</text>
  <text x="280" y="223" text-anchor="middle" fill="#ddd" font-size="10">(Gfi.cpp)</text>

  <!-- Ammeter -->
  <rect x="355" y="190" width="130" height="40" rx="6" fill="#8e44ad" stroke="#6c3483" stroke-width="1.5"/>
  <text x="420" y="210" text-anchor="middle" fill="white">Ammeter/Voltmeter</text>
  <text x="420" y="223" text-anchor="middle" fill="#ddd" font-size="10">(J1772EvseController)</text>

  <!-- EnergyMeter -->
  <rect x="500" y="190" width="130" height="40" rx="6" fill="#d35400" stroke="#a04000" stroke-width="1.5"/>
  <text x="565" y="210" text-anchor="middle" fill="white">EnergyMeter</text>
  <text x="565" y="223" text-anchor="middle" fill="#ddd" font-size="10">(EnergyMeter.cpp)</text>

  <!-- LCD / OBD -->
  <rect x="50" y="310" width="150" height="40" rx="6" fill="#16a085" stroke="#0e6655" stroke-width="1.5"/>
  <text x="125" y="330" text-anchor="middle" fill="white">LCD / OBD</text>
  <text x="125" y="343" text-anchor="middle" fill="#ddd" font-size="10">(LCD.cpp / main.cpp)</text>

  <!-- RAPI Processor -->
  <rect x="300" y="310" width="200" height="40" rx="6" fill="#2980b9" stroke="#1a5276" stroke-width="1.5"/>
  <text x="400" y="330" text-anchor="middle" fill="white">EvseRapiProcessor</text>
  <text x="400" y="343" text-anchor="middle" fill="#ddd" font-size="10">(rapi_proc.cpp)</text>

  <!-- Serial Transport -->
  <rect x="230" y="400" width="130" height="40" rx="6" fill="#27ae60" stroke="#1e8449" stroke-width="1.5"/>
  <text x="295" y="420" text-anchor="middle" fill="white">Serial RAPI</text>
  <text x="295" y="433" text-anchor="middle" fill="#ddd" font-size="10">(EvseSerialRapiProcessor)</text>

  <!-- I2C Transport -->
  <rect x="380" y="400" width="130" height="40" rx="6" fill="#27ae60" stroke="#1e8449" stroke-width="1.5"/>
  <text x="445" y="420" text-anchor="middle" fill="white">I²C RAPI</text>
  <text x="445" y="433" text-anchor="middle" fill="#ddd" font-size="10">(EvseI2cRapiProcessor)</text>

  <!-- MennekesLock -->
  <rect x="650" y="190" width="120" height="40" rx="6" fill="#7f8c8d" stroke="#566573" stroke-width="1.5"/>
  <text x="710" y="210" text-anchor="middle" fill="white">MennekesLock</text>
  <text x="710" y="223" text-anchor="middle" fill="#ddd" font-size="10">(MennekesLock.cpp)</text>

  <!-- Arrows: Main → Controller -->
  <line x1="400" y1="50" x2="400" y2="90" stroke="#aaa" stroke-width="1.5" marker-end="url(#arr)"/>
  <!-- Controller → Pilot -->
  <line x1="310" y1="110" x2="175" y2="190" stroke="#aaa" stroke-width="1.5" marker-end="url(#arr)"/>
  <!-- Controller → GFI -->
  <line x1="350" y1="130" x2="300" y2="190" stroke="#aaa" stroke-width="1.5" marker-end="url(#arr)"/>
  <!-- Controller → Ammeter -->
  <line x1="400" y1="130" x2="410" y2="190" stroke="#aaa" stroke-width="1.5" marker-end="url(#arr)"/>
  <!-- Controller → EnergyMeter -->
  <line x1="470" y1="110" x2="540" y2="190" stroke="#aaa" stroke-width="1.5" marker-end="url(#arr)"/>
  <!-- Controller → Mennekes -->
  <line x1="530" y1="110" x2="680" y2="190" stroke="#aaa" stroke-width="1.5" marker-end="url(#arr)"/>
  <!-- Main → LCD -->
  <line x1="330" y1="50" x2="150" y2="310" stroke="#aaa" stroke-width="1.5" stroke-dasharray="4,3" marker-end="url(#arr)"/>
  <!-- Main → RAPI -->
  <line x1="400" y1="50" x2="400" y2="310" stroke="#aaa" stroke-width="1.5" stroke-dasharray="4,3" marker-end="url(#arr)"/>
  <!-- RAPI → Serial -->
  <line x1="370" y1="350" x2="330" y2="400" stroke="#aaa" stroke-width="1.5" marker-end="url(#arr)"/>
  <!-- RAPI → I2C -->
  <line x1="430" y1="350" x2="450" y2="400" stroke="#aaa" stroke-width="1.5" marker-end="url(#arr)"/>

  <!-- Arrow marker -->
  <defs>
    <marker id="arr" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
      <path d="M0,0 L0,6 L8,3 z" fill="#aaa"/>
    </marker>
  </defs>

  <!-- Legend -->
  <text x="10" y="500" fill="#888" font-size="10">Solid arrows = direct call/ownership  |  Dashed arrows = periodic call</text>
</svg>
```

**Data-flow summary:**

1. `loop()` in `main.cpp` calls `g_EvseController.Update()` every iteration.
2. `Update()` reads the pilot ADC, transitions state, opens/closes the relay, runs GFI checks.
3. Ammeter is sampled inside `Update()` via `readAmmeter()` when charging is active.
4. `EnergyMeter` accumulates Watt-seconds each loop.
5. `loop()` calls `g_OBD.Update()` to refresh the LCD.
6. `loop()` calls `RapiDoCmd()` which dispatches to `g_ESRP.doCmd()` (Serial) and/or `g_EIRP.doCmd()` (I²C).
7. After every RAPI command, `RapiSendEvseState()` is called; if state/flags changed, an `$AT` notification is sent on all active transports.

---

## 4. RAPI Protocol — Complete Reference

### Protocol Format

| Format | Syntax |
|---|---|
| XOR checksum (recommended) | `$cc pp ...^xk\r` |
| Additive checksum (legacy) | `$cc pp ...*ck\r` |
| No checksum (test only) | `$cc pp ...\r` |
| With sequence ID (v3.0.0+) | `$cc pp .. :ss^xk\r` |

Response: `$OK [params] [:ss]^xk\r` or `$NK [params] [:ss]^xk\r`

**Handler dispatch entry point:** `EvseRapiProcessor::processCmd()` in `rapi_proc.cpp`

---

### F-commands (Functions)

| Cmd | Handler (in `processCmd()`) | Action / Side Effects | Example |
|---|---|---|---|
| `$F0 1` | `case 'F'/'0'` | Calls `g_OBD.DisableUpdate(0)` + `g_OBD.Update(OBD_UPD_FORCE)` — re-enables LCD refresh | `$F0 1^43` → `$OK^...` |
| `$F0 0` | `case 'F'/'0'` | Calls `g_OBD.DisableUpdate(1)` — disables LCD refresh | `$F0 0^42` → `$OK^...` |
| `$F1` | `case 'F'/'1'` (needs `BTN_MENU`) | Calls `g_BtnHandler.DoShortPress()` + `g_OBD.Update()` — simulates front-panel button | `$F1^44` → `$OK^...` |
| `$FB color` | `case 'F'/'B'` (needs `LCD16X2`) | Calls `g_OBD.LcdSetBacklightColor(color)` — changes LCD backlight | `$FB 7*03` → `$OK^...` |
| `$FD` | `case 'F'/'D'` | Calls `g_EvseController.Disable()` — opens relay, sets state DISABLED | `$FD*AE` → `$OK^...` |
| `$FE` | `case 'F'/'E'` | Calls `g_EvseController.Enable()` — re-enables EVSE | `$FE*AF` → `$OK^...` |
| `$FF B 0|1` | `case 'F'/'F'` | Calls `g_EvseController.ButtonEnable(u8)` — enables/disables front button | `$FF B 0` → `$OK^...` |
| `$FF D 0|1` | `case 'F'/'F'` | Calls `g_EvseController.EnableDiodeCheck(u8)` — toggles diode check; writes ECF flag to EEPROM | `$FF D 0` → `$OK^...` |
| `$FF E 0|1` | `case 'F'/'F'` | Sets `echo` field — enables/disables character echo on serial | `$FF E 1` → `$OK^...` |
| `$FF F 0|1` | `case 'F'/'F'` (needs `ADVPWR`) | Calls `g_EvseController.EnableGfiSelfTest(u8)` — writes ECF flag to EEPROM | — |
| `$FF G 0|1` | `case 'F'/'F'` (needs `ADVPWR`) | Calls `g_EvseController.EnableGndChk(u8)` — writes ECF flag to EEPROM | `$FF G 1` → `$OK^...` |
| `$FF R 0|1` | `case 'F'/'F'` (needs `ADVPWR`) | Calls `g_EvseController.EnableStuckRelayChk(u8)` — writes ECF flag to EEPROM | — |
| `$FF T 0|1` | `case 'F'/'F'` (needs `TEMPERATURE_MONITORING`) | Calls `g_EvseController.EnableTempChk(u8)` — writes ECF flag to EEPROM | — |
| `$FF V 0|1` | `case 'F'/'F'` | Calls `g_EvseController.EnableVentReq(u8)` — toggles vent-required check; writes ECF flag to EEPROM | — |
| `$FP x y text` | `case 'F'/'P'` (needs `LCD16X2`) | Calls `g_OBD.LcdPrint(x,y,text)` — prints text at LCD position | `$FP 0 0 Hello^...` → `$OK^...` |
| `$FR` | `case 'F'/'R'` | Calls `g_EvseController.Reboot()` — soft reset via watchdog | `$FR*BC` → `$OK^...` |
| `$FS` | `case 'F'/'S'` | Calls `g_EvseController.Sleep()` — graceful sleep (pilot to +12V, relay opens) | `$FS*BD` → `$OK^...` |

---

### S-commands (Set)

| Cmd | Handler | Action / Side Effects | Example |
|---|---|---|---|
| `$S0 0|1` | `case 'S'/'0'` (needs `LCD16X2`+`RGBLCD`) | Calls `g_EvseController.SetBacklightType(BKL_TYPE_MONO|BKL_TYPE_RGB)` — writes EEPROM flag `ECF_MONO_LCD` | `$S0 1*F8` → `$OK^...` |
| `$S1 yr mo day hr min sec` | `case 'S'/'1'` (needs `RTC`) | Calls `SetRTC(...)` — sets DS3231 RTC | `$S1 24 3 12 10 30 0^...` → `$OK^...` |
| `$S2 0|1` | `case 'S'/'2'` (needs `AMMETER`+`ECVF_AMMETER_CAL`) | Calls `g_EvseController.EnableAmmeterCal(u8)` — enables ammeter-always-on calibration mode | `$S2 1*FA` → `$OK^...` |
| `$S3 cnt` | `case 'S'/'3'` (needs `TIME_LIMIT`) | Calls `g_EvseController.SetTimeLimit15(cnt)` — sets charge time limit in 15-min increments; volatile (cleared at disconnect) | `$S3 4^...` → `$OK^...` |
| `$S4 0|1` | `case 'S'/'4'` (needs `AUTH_LOCK`, not `AUTH_LOCK_REG`) | Calls `g_EvseController.AuthLock(v,1)` — sets/clears `ECVF_AUTH_LOCKED` volatile flag | — |
| `$S5 A|M|0|1` | `case 'S'/'5'` (needs `MENNEKES_LOCK`) | Calls `UnlockMennekes()`, `LockMennekes()`, `ClrMennekesManual()`, or `SetMennekesManual()` — controls Type 2 lock actuator | `$S5 A^...` → `$OK^...` |
| `$SA scalefactor offset` | `case 'S'/'A'` (needs `AMMETER`) | Calls `SetCurrentScaleFactor()` + `SetAmmeterCurrentOffset()` — writes calibration to EEPROM | `$SA 220 0^...` → `$OK^...` |
| `$SB` | `case 'S'/'B'` (needs `BOOTLOCK`) | Calls `g_EvseController.ClearBootLock()` — clears boot lock flag; returns `$OK 0` or `$OK 1` | `$SB^...` → `$OK 0^...` |
| `$SC amps [V\|M]` | `case 'S'/'C'` | Calls `g_EvseController.SetCurrentCapacity(amps,1,nosave)` or `SetMaxHwCurrentCapacity(amps)` — updates pilot PWM duty; writes to EEPROM unless V (volatile) | `$SC 32^...` → `$OK 32^...` |
| `$SH kWh` | `case 'S'/'H'` (needs `CHARGE_LIMIT`) | Calls `g_EvseController.SetChargeLimitkWh(kWh)` — sets energy limit; volatile | `$SH 10^...` → `$OK^...` |
| `$SK wh` | `case 'S'/'K'` (needs `KWH_RECORDING`) | Calls `g_EnergyMeter.SetTotkWh(wh)` + `SaveTotkWh()` — writes accumulated kWh to EEPROM | `$SK 0^2C` → `$OK^...` |
| `$SL 1|2|A` | `case 'S'/'L'` | Calls `g_EvseController.SetSvcLevel(1|2,1)` or `EnableAutoSvcLevel(1)` — writes L1/L2 to EEPROM | `$SL 2*15` → `$OK^...` |
| `$SM vscale voffset` | `case 'S'/'M'` (needs `VOLTMETER`) | Calls `g_EvseController.SetVoltmeter(vscale,voffset)` — writes voltmeter calibration to EEPROM | — |
| `$ST sh sm eh em` | `case 'S'/'T'` (needs `DELAYTIMER`) | Calls `g_DelayTimer.SetStartTimer()` + `SetStopTimer()` + `Enable()`; or `Disable()` if all zero — writes to EEPROM | `$ST 0 0 0 0^23` → `$OK^...` |
| `$SV mv` | `case 'S'/'V'` (needs `KWH_RECORDING`, not `VOLTMETER`) | Calls `g_EvseController.SetMV(mv)` — sets voltage for power calculation; volatile | `$SV 223576^...` → `$OK^...` |
| `$SY interval fallback_amps` | `case 'S'/'Y'` (needs `HEARTBEAT_SUPERVISION`) | Calls `g_EvseController.HeartbeatSupervision(interval,current)` — sets watchdog interval; writes to EEPROM | `$SY 100 6^...` → `$OK 100 6 0^...` |
| `$SY` (pulse) | `case 'S'/'Y'` (tokenCnt==1) | Calls `g_EvseController.HsPulse()` — resets heartbeat watchdog timer | `$SY^...` → `$OK^...` |
| `$SY 165` (ack) | `case 'S'/'Y'` (tokenCnt==2) | Calls `g_EvseController.HsAckMissedPulse(0xA5)` — acknowledges missed heartbeat | `$SY A5^...` → `$OK^...` |

---

### G-commands (Get)

| Cmd | Handler | Response | Example |
|---|---|---|---|
| `$G0` | `case 'G'/'0'` | EV connect state: `0`=not connected, `1`=connected, `2`=unknown | `$G0^53` → `$OK 1^...` |
| `$G3` | `case 'G'/'3'` (needs `TIME_LIMIT`) | Charge time limit in 15-min counts | `$G3^50` → `$OK 4^...` |
| `$G4` | `case 'G'/'4'` (needs `AUTH_LOCK`) | Auth lock state `0|1` | `$G4^57` → `$OK 0^...` |
| `$G5` | `case 'G'/'5'` (needs `MENNEKES_LOCK`) | Mennekes lock state + mode | `$G5^56` → `$OK 1 A^...` |
| `$GA` | `case 'G'/'A'` (needs `AMMETER`) | `currentscalefactor currentoffset` | `$GA^22` → `$OK 220 0^...` |
| `$GC` | `case 'G'/'C'` | `minamps hmaxamps pilotamps cmaxamps` | `$GC^20` → `$OK 6 32 32 32^...` |
| `$GD` | `case 'G'/'D'` (needs `DELAYTIMER`) | `starthr startmin endhr endmin` | `$GD^27` → `$OK 0 0 0 0^...` |
| `$GE` | `case 'G'/'E'` | `amps(dec) flags(hex)` — current capacity and ECF flags | `$GE^26` → `$OK 32 0000^...` |
| `$GF` | `case 'G'/'F'` | `gfitripcnt nogndtripcnt stuckrelaytripcnt` (all hex) | `$GF^25` → `$OK 00 00 00^...` |
| `$GG` | `case 'G'/'G'` | `milliamps millivolts` (−1 if no ammeter/voltmeter) | `$GG^24` → `$OK 16000 230000^...` |
| `$GH` | `case 'G'/'H'` (needs `CHARGE_LIMIT`) | kWh charge limit (`0`=none) | `$GH^2B` → `$OK 0^...` |
| `$GI` | `case 'G'/'I'` (needs `MCU_ID_LEN`) | MCU serial number (6 ASCII + 4 hex) | `$GI^28` → `$OK ABCDEF00FF^...` |
| `$GM` | `case 'G'/'M'` (needs `VOLTMETER`) | `voltscalefactor voltoffset` | `$GM^2E` → `$OK 1 0^...` |
| `$GO` | `case 'G'/'O'` (needs `TEMPERATURE_MONITORING`) | `ambientthresh irthresh` in 10ths °C | `$GO^2C` → `$OK 650 900^...` |
| `$GP` | `case 'G'/'P'` (needs `TEMPERATURE_MONITORING`) | `ds3231temp lm75btemp tmp007temp` in 10ths °C | `$GP^33` → `$OK 250 -2560 -2560^...` |
| `$GS` | `case 'G'/'S'` | `evsestate(hex) elapsed(sec) pilotstate(hex) vflags(hex)` | `$GS^30` → `$OK 03 120 03 0040^...` |
| `$GT` | `case 'G'/'T'` (needs `RTC`) | `yr mo day hr min sec` | `$GT^37` → `$OK 24 3 12 10 30 0^...` |
| `$GU` | `case 'G'/'U'` (needs `KWH_RECORDING`) | `Wattseconds Whacc` | `$GU^36` → `$OK 3600000 1000^...` |
| `$GV` | `case 'G'/'V'` | `firmware_version protocol_version` | `$GV^35` → `$OK 8.2.3 5.2.1-LGT^...` |
| `$GY` | `case 'G'/'Y'` (needs `HEARTBEAT_SUPERVISION`) | `interval fallback_current trigger` | `$GY^...` → `$OK 100 6 0^...` |

---

### T-commands (Test/Debug — needs `RAPI_T_COMMANDS`)

| Cmd | Handler | Action | Example |
|---|---|---|---|
| `$T0 amps` | `case 'T'/'0'` (needs `FAKE_CHARGING_CURRENT`) | Calls `g_EvseController.SetChargingCurrent(amps*1000)` + `g_OBD.SetAmmeterDirty(1)` — injects fake current reading | `$T0 75^...` → `$OK^...` |

---

### Z-commands (Hardware Tuning — needs `RELAY_HOLD_DELAY_TUNING`)

| Cmd | Handler | Action | Example |
|---|---|---|---|
| `$Z0 closems holdpwm` | `case 'Z'/'0'` | Calls `g_EvseController.setPwmPinParms(closems,holdpwm)` + writes `EOFS_RELAY_CLOSE_MS` / `EOFS_RELAY_HOLD_PWM` to EEPROM | `$Z0 20 128^...` → `$OK^...` |

---

### Asynchronous Notifications (EVSE → Host)

| Message | Sender | Trigger |
|---|---|---|
| `$AB postcode fwrev` | `sendBootNotification()` → `RapiSendBootNotification()` | On boot completion |
| `$AT evsestate pilotstate currentcapacity vflags` | `sendEvseState()` → `RapiSendEvseState()` | Any state/capacity/vflags change |
| `$AN type` | `sendButtonPress(long_press)` → `RapiSendButtonPress()` | Front-panel button press (needs `RAPI_BTN`) |
| `$WF mode` | `setWifiMode(mode)` → `RapiSetWifiMode()` | Long-press WiFi-reset button (needs `RAPI_WF`) |

---

### Transport Differences

| Feature | Serial (`EvseSerialRapiProcessor`) | I²C (`EvseI2cRapiProcessor`) |
|---|---|---|
| Transport class | Uses `Serial.available()` / `Serial.read()` / `Serial.write()` | Uses `Wire.available()` / `Wire.read()` / `Wire.beginTransmission()` + `Wire.endTransmission()` |
| Init | `Serial` must be pre-initialised by `setup()` | Calls `Wire.begin(RAPI_I2C_LOCAL_ADDR)` + registers `receiveEvent` ISR |
| Echo mode | Supported (character echo + LF) | **Not recommended** — comment in code says "DO NOT USE on I2C" |
| Timing | No artificial delay | 6 ms minimum delay between `doCmd()` calls (prevents I²C starvation) |
| ISR | None | `receiveEvent()` is ISR — only collects bytes, no processing |

---

## 5. Car Connection & Interaction

### Sequence: State A → B (Car Plugs In)

1. **Pilot ADC read** — `J1772EVSEController::Update()` (`J1772EvseController.cpp`) calls `m_Pilot.GetState()` which reads the ADC voltage on the pilot pin.
2. **Voltage threshold** — pilot drops from +12 V to +9 V; `m_TmpPilotState` transitions to `EVSE_STATE_B`.
3. **Debounce** — `Update()` waits for `m_TmpPilotStateStart` to be stable for `PILOT_SETTLE_MS` before committing.
4. **State commit** — `m_EvseState = EVSE_STATE_B`; sets `ECVF_EV_CONNECTED` in `m_wVFlags`.
5. **Mennekes lock** — if `MENNEKES_LOCK` and automatic mode: `m_MennekesLock.Lock()` is called.
6. **LCD update** — `g_OBD.Update()` in main loop shows "Connected" message.
7. **RAPI notification** — `RapiSendEvseState()` sends `$AT 02 02 32 0100` (state B, pilot B, 32A, EV connected flag).

### Sequence: State B → C (Car Requests Charging)

1. **Pilot drops to +6 V** — `m_TmpPilotState = EVSE_STATE_C`.
2. **Safety pre-checks** in `Update()`:
   - GFI: `m_Gfi.SelfTest()` (if enabled).
   - Stuck relay: verifies relay was open before closing.
   - Ground check: reads `ACLINE1/ACLINE2` pins.
   - Auth lock: checks `ECVF_AUTH_LOCKED`.
   - Delay timer / boot lock: checks `ECVF_BOOT_LOCK`, timer state.
3. **Relay close** — `chargingOn()` → sets `CHARGING_REG`/`CHARGING2_REG` pins high; sets `ECVF_CHARGING_ON`; records `m_ChargeOnTimeMS = millis()`.
4. **PWM relay drive** — if `RELAY_PWM`, applies full DC for `m_relayCloseMs` ms, then drops to `m_relayHoldPwm` PWM to save power.
5. **Energy meter** — `g_EnergyMeter` starts accumulating Watt-seconds.
6. **LCD update** — shows charging current and energy.
7. **RAPI notification** — `$AT 03 03 32 0040` (state C, charging on).

### Sequence: Current-Limit Request (`$SC amps`)

1. RAPI dispatcher calls `g_EvseController.SetCurrentCapacity(amps, 1, nosave)`.
2. `SetCurrentCapacity()` clamps to `[MIN_CURRENT_CAPACITY, m_MaxHwCurrentCapacity]`.
3. Calls `m_Pilot.SetPWM(amps)` — updates Timer1 OCR register to change duty cycle immediately.
4. If `nosave=0`, writes new value to EEPROM (`EOFS_CURRENT_CAPACITY_L1` or `EOFS_CURRENT_CAPACITY_L2`).
5. Returns resultant amps in `$OK ampsset`.
6. `RapiSendEvseState()` notifies `$AT` with new capacity.

### Sequence: Disconnect (State C/B → A)

1. **Pilot rises to +12 V** — `m_TmpPilotState = EVSE_STATE_A`.
2. **Relay open** — `chargingOff()` → clears relay pins; clears `ECVF_CHARGING_ON`; records `m_ChargeOffTimeMS`.
3. **Energy meter** — `g_EnergyMeter` finalises session Watt-seconds; updates `m_TotkWh` and saves to EEPROM.
4. **Mennekes unlock** — if automatic mode: `m_MennekesLock.Unlock()`.
5. **Limits cleared** — time-limit and charge-limit volatile flags cleared.
6. **RAPI** — `$AT 01 01 32 0000` (state A, not charging).

---

## 6. ESP / RAPI Transport

### Transports Instantiated

Controlled entirely by `#define` build flags:

- `RAPI_SERIAL` — creates global `g_ESRP` (`EvseSerialRapiProcessor`). Enabled in all `platformio.ini` environments.
- `RAPI_I2C` — creates global `g_EIRP` (`EvseI2cRapiProcessor`). Not enabled by default in `platformio.ini` but available.

### Message Routing

`RapiDoCmd()` (called from `loop()`) calls each active transport's `doCmd()` in sequence:
```
RapiDoCmd()
  ├── g_ESRP.doCmd()   [if RAPI_SERIAL]
  └── g_EIRP.doCmd()   [if RAPI_I2C, with 6ms throttle]
```

`RapiSendEvseState()` and `RapiSendBootNotification()` broadcast to **all** active transports simultaneously.

### I²C Slave Operation

The AVR acts as an **I²C slave** at address `RAPI_I2C_LOCAL_ADDR`. The master (e.g., ESP) writes a RAPI command string byte-by-byte. The `receiveEvent` ISR (registered via `Wire.onReceive()`) is intentionally empty — byte collection happens in `EvseI2cRapiProcessor::doCmd()` by polling `Wire.available()`. Responses are written back using `Wire.beginTransmission(RAPI_I2C_REMOTE_ADDR)` / `Wire.endTransmission()`.

---

## 7. Module API (Short Reference)

### `J1772EVSEController` (`J1772EvseController.h/.cpp`)
Core state machine. Most important public methods:

| Function | Behavior |
|---|---|
| `Init()` | Reads EEPROM flags, initialises pilot/GFI/relay pins, runs POST |
| `Update(forcetransition)` | Main periodic function: reads pilot ADC, transitions states, manages relay |
| `Enable()` | Clears DISABLED state, re-enters normal operation |
| `Disable()` | Immediately opens relay, sets `EVSE_STATE_DISABLED` |
| `Sleep()` | Graceful sleep: sends pilot to +12V first, then opens relay |
| `SetCurrentCapacity(amps, updpilot, nosave)` | Clamps and sets charge current; optionally writes EEPROM and updates PWM |
| `SetSvcLevel(level, save)` | Sets L1 or L2 service level; writes EEPROM |
| `GetState()` | Returns current `EVSE_STATE_xxx` byte |
| `GetVFlags()` | Returns volatile flag word (`ECVF_xxx`) |
| `HsPulse()` | Pets the heartbeat supervision watchdog |
| `HeartbeatSupervision(interval, fallback)` | Configures heartbeat watchdog; writes EEPROM |

### `J1772Pilot` (`J1772Pilot.h/.cpp`)
Generates and reads J1772 pilot signal.

| Function | Behavior |
|---|---|
| `Init()` | Configures Timer1 for 1 kHz PWM on pilot pin |
| `SetState(state)` | Sets pilot to +12V (State A), PWM (States B/C), or −12V |
| `GetState()` | Reads ADC on pilot pin; classifies as `EVSE_STATE_x` based on thresholds |
| `SetPWM(amps)` | Calculates and loads OCR1A/OCR1B for given current in amps |

### `Gfi` (`Gfi.h/.cpp`)
GFI ground-fault detection.

| Function | Behavior |
|---|---|
| `Init()` | Configures GFI interrupt pin and test pin |
| `SelfTest()` | Pulses test coil, expects trip; returns pass/fail |
| `Fault()` | ISR-called; sets GFI fault flag |
| `Reset()` | Clears fault flag after safe interval |

### `EnergyMeter` (`EnergyMeter.h/.cpp`)

| Function | Behavior |
|---|---|
| `Update(milliamps, millivolts)` | Accumulates Watt-seconds for this session |
| `GetSessionWs()` | Returns session Watt-seconds |
| `GetTotkWh()` | Returns total accumulated Wh from EEPROM |
| `SaveTotkWh()` | Persists accumulated Wh to EEPROM (`EOFS_KWH_ACCUMULATED`) |

### `EvseRapiProcessor` (`rapi_proc.h/.cpp`)

| Function | Behavior |
|---|---|
| `doCmd()` | Polls transport, assembles command bytes, calls `processCmd()` |
| `processCmd()` | Tokenises and dispatches RAPI command; sends response |
| `sendEvseState()` | Formats and sends `$AT` notification |
| `sendBootNotification()` | Formats and sends `$AB` notification |

---

## 8. State Machine & Timing

### EVSE States

| State | Hex | Description |
|---|---|---|
| `EVSE_STATE_UNKNOWN` | `0x00` | Initial / transitional |
| `EVSE_STATE_A` | `0x01` | Vehicle not connected (+12V pilot) |
| `EVSE_STATE_B` | `0x02` | Vehicle connected, not charging (+9V pilot) |
| `EVSE_STATE_C` | `0x03` | Charging (+6V pilot, relay closed) |
| `EVSE_STATE_D` | `0x04` | Vent required (+3V pilot) — fault |
| `EVSE_STATE_DIODE_CHK_FAILED` | `0x05` | Diode check failure |
| `EVSE_STATE_GFCI_FAULT` | `0x06` | GFI trip |
| `EVSE_STATE_NO_GROUND` | `0x07` | Open ground detected |
| `EVSE_STATE_STUCK_RELAY` | `0x08` | Relay did not open |
| `EVSE_STATE_GFI_TEST_FAILED` | `0x09` | GFI self-test failure |
| `EVSE_STATE_OVER_TEMPERATURE` | `0x0A` | Over-temperature shutdown |
| `EVSE_STATE_OVER_CURRENT` | `0x0B` | Over-current shutdown |
| `EVSE_STATE_RELAY_CLOSURE_FAULT` | `0x0E` | Relay failed to close |
| `EVSE_STATE_SLEEPING` | `0xFE` | Timer sleep |
| `EVSE_STATE_DISABLED` | `0xFF` | Manually disabled |

Fault states: `0x04`–`0x0E` (`EVSE_FAULT_STATE_BEGIN` to `EVSE_FAULT_STATE_END`).

### Key Transitions (all in `J1772EVSEController::Update()`)

| From | To | Condition | Function |
|---|---|---|---|
| Any | `EVSE_STATE_A` | Pilot ADC reads +12V | `Update()` |
| `EVSE_STATE_A` | `EVSE_STATE_B` | Pilot ADC reads +9V | `Update()` |
| `EVSE_STATE_B` | `EVSE_STATE_C` | Pilot ADC reads +6V + all safety checks pass | `Update()` → `chargingOn()` |
| `EVSE_STATE_C` | `EVSE_STATE_B` | EV signals done (pilot back to +9V) | `Update()` → `chargingOff()` |
| Any | `EVSE_STATE_GFCI_FAULT` | GFI interrupt fires | `Gfi::Fault()` ISR → `Update()` |
| Any | `EVSE_STATE_NO_GROUND` | Ground-check pins open | `Update()` (POST and runtime) |
| Any | `EVSE_STATE_STUCK_RELAY` | Relay voltage detected when should be open | `Update()` (POST) |
| Any | `EVSE_STATE_OVER_TEMPERATURE` | Any temperature sensor > threshold | `Update()` (temperature monitor) |
| Any | `EVSE_STATE_OVER_CURRENT` | Ammeter > `OVERCURRENT_THRESHOLD` for `OVERCURRENT_TIMEOUT` ms | `Update()` (EU only) |
| Any | `EVSE_STATE_SLEEPING` | Delay timer fires or limit reached | `Update()` |
| Any | `EVSE_STATE_DISABLED` | `$FD` RAPI or `Disable()` | `Disable()` |

### Debounce / Timing

- Pilot state transitions use a debounce timer (`m_TmpPilotStateStart`) — state must be stable for `PILOT_SETTLE_MS` (defined in `open_evse.h`).
- GFI retry: `m_GfiRetryCnt` / `m_GfiFaultStartMs` — limited auto-reset attempts before hard fault.
- No-ground retry: `m_NoGndRetryCnt` / `m_NoGndStart`.
- Heartbeat supervision: configurable interval in seconds; fallback current applied if no pulse received.

---

## 9. Safety & Failure Modes

| Safety Check | Mechanism | Enforcement Point | EEPROM |
|---|---|---|---|
| **GFI** | Hardware interrupt on GFI pin → `Gfi::Fault()` sets flag; `Update()` opens relay | `Gfi.cpp::Fault()`, `J1772EvseController.cpp::Update()` | Trip count: `EOFS_GFI_TRIP_CNT` |
| **GFI Self-Test** | `Gfi::SelfTest()` pulses coil before each charge; expects trip within timeout | `J1772EvseController.cpp::Update()` | Disabled flag: `ECF_GFI_TEST_DISABLED` |
| **Ground Check** | Reads `ACLINE1/ACLINE2` pins; open = fault | `Update()` (POST + runtime, needs `ADVPWR`) | Trip count: `EOFS_NOGND_TRIP_CNT` |
| **Stuck Relay** | Measures voltage on relay pins before closure; relay should read 0 V | `Update()` POST phase (`doPost()`) | Trip count: `EOFS_STUCK_RELAY_TRIP_CNT` |
| **Diode Check** | Measures negative pilot voltage; missing negative swing = shorted diode | `Update()` before closing relay | Disabled flag: `ECF_DIODE_CHK_DISABLED` |
| **Vent Required** | State D (+3V pilot) triggers fault | `Update()` | Disabled flag: `ECF_VENT_REQ_DISABLED` |
| **Over-Temperature** | Polls LM75B/MCP9808/TMP007/DS3231; compares against thresholds | `Update()` temperature monitor section | Disabled flag: `ECF_TEMP_CHK_DISABLED` |
| **Over-Current** | Ammeter > `OVERCURRENT_THRESHOLD` for `OVERCURRENT_TIMEOUT` ms | `Update()` (EU build, `OVERCURRENT_THRESHOLD` defined) | None (volatile) |
| **Auth Lock** | `ECVF_AUTH_LOCKED` flag prevents `B→C` transition | `Update()` | Volatile (not saved) |
| **Boot Lock** | `ECVF_BOOT_LOCK` prevents charging until `$SB` RAPI command received | `Update()`, cleared by `ClearBootLock()` | Volatile |
| **Heartbeat Supervision** | Watchdog: if no `$SY` pulse within interval, limits current to fallback amps | `Update()` → `HsCheck()` | Interval/fallback: EEPROM |
| **EEPROM writes** | Use `eeprom_write_byte()`/`eeprom_write_word()` with address offsets `EOFS_*` from `open_evse.h` | Throughout `J1772EvseController.cpp` and `EnergyMeter.cpp` | See `EOFS_*` defines |

---

## 10. Tests & Gaps

### Existing Test / Debug Vectors

- **`RAPI_T_COMMANDS` + `FAKE_CHARGING_CURRENT`** — `$T0 amps` injects a fake ammeter reading without real hardware. Good for testing LCD display and energy meter at a workbench.
- **`RELAY_HOLD_DELAY_TUNING`** — `$Z0 closems holdpwm` tunes relay PWM parameters live and writes to EEPROM.
- **`S2` ammeter calibration mode** — keeps ammeter running even when relay is open.
- **`$FF E 1`** — echo mode for interactive terminal testing.
- **PlatformIO build matrix** (`openevse`, `openevse_eu`, `emonevse`, `openevse_v6`) — compile-time coverage across feature combinations.
- **CI workflows** (`build_platformio.yml`, `build_arduino.yml`) — compile-only validation for all environments.

### Gaps / Missing Coverage

- **No unit tests** — there is no test framework (no `test/` directory). All testing is compile-only or manual on hardware.
- **No simulation harness** — the pilot ADC reading is only testable on real hardware; no mock ADC injection mechanism exists (unlike current, which has `FAKE_CHARGING_CURRENT`).
- **GFI self-test not auto-verified** — test result is hardware-dependent; no software simulation path.
- **I²C RAPI not CI-tested** — `RAPI_I2C` is never built in CI workflows; integration untested.
- **Heartbeat Supervision timing** — tested only via real time (`millis()`); no accelerated simulation.

### Recommended Test Vectors

| Vector | Command Sequence | Expected Response |
|---|---|---|
| Firmware version | `$GV^35` | `$OK 8.2.3 5.2.1-LGT^XX` |
| Get state (idle) | `$GS^30` | `$OK 01 0 01 0000^XX` |
| Set 16A (volatile) | `$SC 16 V^XX` | `$OK 16^XX` |
| Set 16A (persistent) | `$SC 16^XX` | `$OK 16^XX` |
| Get current info | `$GC^20` | `$OK 6 32 16 32^XX` |
| Disable EVSE | `$FD*AE` | `$OK^XX` then `$AT FF ...^XX` |
| Enable EVSE | `$FE*AF` | `$OK^XX` then `$AT 01 ...^XX` |
| Inject 20A fake current | `$T0 20^XX` (needs `RAPI_T_COMMANDS`) | `$OK^XX` |
| Read energy | `$GU^36` | `$OK <ws> <whacc>^XX` |
| Clear accumulated kWh | `$SK 0^2C` | `$OK^XX` |
| Heartbeat pulse | `$SY^XX` | `$OK 0 0 0^XX` (if HS disabled) |
| Set HS params | `$SY 100 6^XX` | `$OK 100 6 0^XX` |

---

## 11. Machine Artifact

```json
{
  "F0": {
    "command": "$F0 0|1",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["LCD update enable/disable", "g_OBD.DisableUpdate()", "g_OBD.Update()"]
  },
  "F1": {
    "command": "$F1",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["simulates button short press", "g_BtnHandler.DoShortPress()", "g_OBD.Update()"]
  },
  "FB": {
    "command": "$FB color",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["LCD backlight color change", "g_OBD.LcdSetBacklightColor()"]
  },
  "FD": {
    "command": "$FD",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["relay open", "state=EVSE_STATE_DISABLED", "g_EvseController.Disable()"]
  },
  "FE": {
    "command": "$FE",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["EVSE re-enabled", "g_EvseController.Enable()"]
  },
  "FF": {
    "command": "$FF feature 0|1",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["feature flag toggle", "may write EEPROM ECF flags", "EnableDiodeCheck/EnableGndChk/EnableGfiSelfTest/EnableStuckRelayChk/EnableTempChk/EnableVentReq/ButtonEnable"]
  },
  "FP": {
    "command": "$FP x y text",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["LCD text update", "g_OBD.LcdPrint()"]
  },
  "FR": {
    "command": "$FR",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["MCU reboot via watchdog", "g_EvseController.Reboot()"]
  },
  "FS": {
    "command": "$FS",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["graceful sleep", "relay open", "pilot +12V", "g_EvseController.Sleep()"]
  },
  "S0": {
    "command": "$S0 0|1",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["EEPROM write ECF_MONO_LCD flag", "SetBacklightType()"]
  },
  "S1": {
    "command": "$S1 yr mo day hr min sec",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["RTC DS3231 time set", "SetRTC()"]
  },
  "S2": {
    "command": "$S2 0|1",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["ammeter calibration mode toggle", "EnableAmmeterCal()"]
  },
  "S3": {
    "command": "$S3 cnt",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["volatile charge time limit set", "SetTimeLimit15()", "LCD refresh"]
  },
  "S4": {
    "command": "$S4 0|1",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["auth lock flag ECVF_AUTH_LOCKED set/cleared", "AuthLock()"]
  },
  "S5": {
    "command": "$S5 A|M|0|1",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["Mennekes lock actuator control", "LockMennekes/UnlockMennekes/SetMennekesManual/ClrMennekesManual"]
  },
  "SA": {
    "command": "$SA scalefactor offset",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["ammeter calibration EEPROM write", "SetCurrentScaleFactor/SetAmmeterCurrentOffset"]
  },
  "SB": {
    "command": "$SB",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["boot lock cleared", "ClearBootLock()"]
  },
  "SC": {
    "command": "$SC amps [V|M]",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["pilot PWM updated", "optionally writes EEPROM EOFS_CURRENT_CAPACITY_L1/L2", "SetCurrentCapacity/SetMaxHwCurrentCapacity"]
  },
  "SH": {
    "command": "$SH kWh",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["volatile charge energy limit set", "SetChargeLimitkWh()"]
  },
  "SK": {
    "command": "$SK wh",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["accumulated kWh reset", "EEPROM write EOFS_KWH_ACCUMULATED", "SetTotkWh/SaveTotkWh"]
  },
  "SL": {
    "command": "$SL 1|2|A",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["service level EEPROM write ECF_L2", "SetSvcLevel/EnableAutoSvcLevel"]
  },
  "SM": {
    "command": "$SM vscale voffset",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["voltmeter calibration EEPROM write", "SetVoltmeter()"]
  },
  "ST": {
    "command": "$ST sh sm eh em",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["delay timer set/cleared", "EEPROM write timer times", "DelayTimer.SetStartTimer/SetStopTimer/Enable/Disable"]
  },
  "SV": {
    "command": "$SV mv",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["volatile voltage set for energy calculation", "SetMV()"]
  },
  "SY": {
    "command": "$SY [interval fallback | | 165]",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["heartbeat supervision config or pulse or ack", "EEPROM write interval/fallback", "HeartbeatSupervision/HsPulse/HsAckMissedPulse"]
  },
  "G0": {
    "command": "$G0",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["read-only: returns ECVF_EV_CONNECTED flag"]
  },
  "G3": {
    "command": "$G3",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["read-only: returns m_timeLimit15"]
  },
  "G4": {
    "command": "$G4",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["read-only: returns ECVF_AUTH_LOCKED"]
  },
  "G5": {
    "command": "$G5",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["read-only: returns Mennekes lock state and mode"]
  },
  "GA": {
    "command": "$GA",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["read-only: returns ammeter calibration values"]
  },
  "GC": {
    "command": "$GC",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["read-only: returns min/max/pilot/configured current capacity"]
  },
  "GD": {
    "command": "$GD",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["read-only: returns delay timer start/end times"]
  },
  "GE": {
    "command": "$GE",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["read-only: returns current capacity and ECF flags"]
  },
  "GF": {
    "command": "$GF",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["read-only: returns GFI/no-ground/stuck-relay trip counters"]
  },
  "GG": {
    "command": "$GG",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["read-only: returns milliamps and millivolts"]
  },
  "GH": {
    "command": "$GH",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["read-only: returns charge energy limit in kWh"]
  },
  "GI": {
    "command": "$GI",
    "handler": "EvseRapiProcessor::processCmd / getMcuId()",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["read-only: reads AVR boot signature bytes for MCU serial number"]
  },
  "GM": {
    "command": "$GM",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["read-only: returns voltmeter calibration values"]
  },
  "GO": {
    "command": "$GO",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["read-only: returns over-temperature thresholds"]
  },
  "GP": {
    "command": "$GP",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["read-only: returns DS3231/LM75B/TMP007 temperatures"]
  },
  "GS": {
    "command": "$GS",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["read-only: returns evsestate, elapsed, pilotstate, vflags"]
  },
  "GT": {
    "command": "$GT",
    "handler": "EvseRapiProcessor::processCmd / GetRTC()",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["read-only: reads DS3231 RTC current time"]
  },
  "GU": {
    "command": "$GU",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["read-only: returns session Watt-seconds and accumulated kWh"]
  },
  "GV": {
    "command": "$GV",
    "handler": "EvseRapiProcessor::processCmd / GetVerStr()",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["read-only: returns firmware and RAPI protocol version strings"]
  },
  "GY": {
    "command": "$GY",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["read-only: returns heartbeat supervision interval, fallback current, trigger state"]
  },
  "T0": {
    "command": "$T0 amps",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["debug only: sets fake charging current", "SetChargingCurrent()", "OBD ammeter dirty flag", "requires RAPI_T_COMMANDS + FAKE_CHARGING_CURRENT"]
  },
  "Z0": {
    "command": "$Z0 closems holdpwm",
    "handler": "EvseRapiProcessor::processCmd",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["relay PWM tuning", "EEPROM write EOFS_RELAY_CLOSE_MS + EOFS_RELAY_HOLD_PWM", "setPwmPinParms()", "requires RELAY_HOLD_DELAY_TUNING"]
  },
  "$AB": {
    "command": "$AB postcode fwrev",
    "handler": "EvseRapiProcessor::sendBootNotification / RapiSendBootNotification",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["async notification: sent on boot to all active transports"]
  },
  "$AT": {
    "command": "$AT evsestate pilotstate currentcapacity vflags",
    "handler": "EvseRapiProcessor::sendEvseState / RapiSendEvseState",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["async notification: sent whenever EVSE state or vflags change"]
  },
  "$AN": {
    "command": "$AN type",
    "handler": "EvseRapiProcessor::sendButtonPress / RapiSendButtonPress",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["async notification: sent on front-panel button press (requires RAPI_BTN)"]
  },
  "$WF": {
    "command": "$WF mode",
    "handler": "EvseRapiProcessor::setWifiMode / RapiSetWifiMode",
    "file": "firmware/open_evse/rapi_proc.cpp",
    "side_effects": ["async notification: requests WiFi mode change on connected host (requires RAPI_WF)"]
  }
}
```

---

*Generated from source code analysis of commit on branch `copilot/analyze-project-structure`. All source file paths are relative to the repository root.*
