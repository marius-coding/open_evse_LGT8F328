# Firmware Behavior Research Pack

This document captures key firmware behaviors that the simulator must reproduce
faithfully for ESP interoperability.  It is the output of Step 10 of the
simulation plan and provides:

1. [Command Compatibility Table](#1-command-compatibility-table)
2. [EVSE State Mapping Table](#2-evse-state-mapping-table)
3. [Known Intentional Simplifications](#3-known-intentional-simplifications)

Source documents used for this research:

| File | Purpose |
|------|---------|
| [`firmware/open_evse/rapi_proc.h`](../../../../firmware/open_evse/rapi_proc.h) | RAPI protocol framing, checksum conventions, sequence IDs |
| [`firmware/open_evse/rapi_proc.cpp`](../../../../firmware/open_evse/rapi_proc.cpp) | `doCmd` tokenizer, response builder, command handlers, async notifications |
| [`firmware/open_evse/J1772EvseController.h`](../../../../firmware/open_evse/J1772EvseController.h) | State constants (`EVSE_STATE_*`), volatile flag constants (`ECVF_*`) |
| [`firmware/open_evse/J1772EvseController.cpp`](../../../../firmware/open_evse/J1772EvseController.cpp) | State-transition logic (lines 1253–1601), fault-entry paths (lines 1348–1510) |
| [`firmware/open_evse/open_evse.h`](../../../../firmware/open_evse/open_evse.h) | `SERIAL_BAUD`, debounce constants (lines 587–590), LCD colour constants (lines 640–646), version string |
| [`firmware/open_evse/main.cpp`](../../../../firmware/open_evse/main.cpp) | `OnboardDisplay::Update()` (lines 506–980), `Serial.begin()` setup (lines 2479–2481) |
| [`firmware/open_evse/Language_default.h`](../../../../firmware/open_evse/Language_default.h) | English display string macros (`STR_READY`, `STR_CHARGING`, …) |
| [`firmware/open_evse/strings.h`](../../../../firmware/open_evse/strings.h) / [`strings.cpp`](../../../../firmware/open_evse/strings.cpp) | PROGMEM string objects (`g_psReady`, `g_psCharging`, …) |
| [`README.md`](../../../../README.md) | Project overview and build instructions |
| [`firmware/open_evse/LoadingFirmware.md`](../../../../firmware/open_evse/LoadingFirmware.md) | Factory flashing and fuse-bit instructions |

---

## 1. Command Compatibility Table

MVP commands implemented in `rapi_dispatch.py`.  The **Firmware source** column
links to the relevant lines in `rapi_proc.cpp`.

| Command | Direction | Description | Firmware source | Simulator status |
|---------|-----------|-------------|-----------------|-----------------|
| `GV` | ESP→EVSE | Get firmware + RAPI version | rapi_proc.cpp:798–802 | ✅ Implemented |
| `GS` | ESP→EVSE | Get EVSE state, elapsed charge time, pilot state, volatile flags | rapi_proc.cpp:775–779 | ✅ Implemented |
| `GE` | ESP→EVSE | Get current capacity and non-volatile settings flags | rapi_proc.cpp:700–703 | ✅ Implemented |
| `GC` | ESP→EVSE | Get current capacity range (min, hw-max, current, cap) | rapi_proc.cpp:648–659 | ✅ Implemented |
| `G0` | ESP→EVSE | Get EV connect state (0=disconnected, 1=connected, 2=unknown) | rapi_proc.cpp:602–614 | ✅ Implemented |
| `SC` | ESP→EVSE | Set charge current capacity (amps); responds with applied value | rapi_proc.cpp:461–512 | ✅ Implemented |
| `FE` | ESP→EVSE | Enable EVSE (transitions DISABLED/SLEEPING → state A) | rapi_proc.cpp:300–302 | ✅ Implemented |
| `FD` | ESP→EVSE | Disable EVSE (transitions to DISABLED) | rapi_proc.cpp:297–299 | ✅ Implemented |
| `SL` | ESP→EVSE | Set service level (1 or 2) | rapi_proc.cpp:513–535 | ✅ Implemented |
| `AB` | EVSE→ESP | Async boot notification: state + firmware version | rapi_proc.cpp:151–162 | ✅ Implemented |
| `AT` | EVSE→ESP | Async state-change notification: state, pilot, current, vflags | rapi_proc.cpp:164–173 | ✅ Implemented |

### Response framing rules (rapi_proc.h / rapi_proc.cpp:109–241)

| Rule | Firmware behavior | Simulator behavior |
|------|------------------|--------------------|
| Start-of-command | `$` (0x24) | Same |
| End-of-command | `\r` (0x0D) | Same |
| XOR checksum delimiter | `^` followed by two uppercase hex digits | Same |
| Additive checksum delimiter | `*` followed by two uppercase hex digits | Accepted on input; simulator always emits XOR checksums |
| Sequence ID | ` :XX` appended before checksum when present in request | Echoed in response when request carries one |
| `$OK` response | Command succeeded; optional payload follows `OK` | Same |
| `$NK` response | Command failed or unknown | Same; emitted for unsupported commands and bad arguments |
| Buffer limit | `ESRAPI_BUFLEN = 32` chars | Same; `RapiStreamParser` discards overlong frames |
| Max args | `ESRAPI_MAX_ARGS = 10` | Same |

---

## 2. EVSE State Mapping Table

### 2a. State constants

Mirrors `J1772EvseController.h` and `open_evse.h`.

| Constant | Hex | Meaning | LCD color | LCD line 1 | LCD line 2 |
|----------|-----|---------|-----------|-----------|-----------|
| `EVSE_STATE_UNKNOWN` | `0x00` | Unknown / unset | — | — | — |
| `EVSE_STATE_A` | `0x01` | Not connected (12 V) | GREEN (`0x2`) | "Ready" | "" |
| `EVSE_STATE_B` | `0x02` | Connected, not charging (9 V) | YELLOW (`0x3`) | "Connected" | "" |
| `EVSE_STATE_C` | `0x03` | Charging (6 V) | TEAL (`0x6`) | "Charging" | "" |
| `EVSE_STATE_D` | `0x04` | Vent required (3 V) | RED (`0x1`) | "EVSE ERROR" | "VENT REQUIRED" |
| `EVSE_STATE_DIODE_CHK_FAILED` | `0x05` | Diode check failed | RED (`0x1`) | "EVSE ERROR" | "DIODE CHECK" |
| `EVSE_STATE_GFCI_FAULT` | `0x06` | GFCI/GFI fault | RED (`0x1`) | "GFCI FAULT" | "" |
| `EVSE_STATE_NO_GROUND` | `0x07` | No ground detected | RED (`0x1`) | "NO GROUND" | "" |
| `EVSE_STATE_STUCK_RELAY` | `0x08` | Stuck relay detected | RED (`0x1`) | "EVSE ERROR" | "STUCK RELAY" |
| `EVSE_STATE_SLEEPING` | `0xFE` | Sleeping (timer/limit) | VIOLET (`0x5`) or WHITE (`0x7`) if EV connected | "Sleeping" | "" |
| `EVSE_STATE_DISABLED` | `0xFF` | Disabled by command | VIOLET (`0x5`) | "Disabled" | "" |

Color constants source: `firmware/open_evse/open_evse.h:640–646`
Display logic source: `firmware/open_evse/main.cpp:529–773`
String values source: `firmware/open_evse/Language_default.h` (macros) → `strings.cpp` (PROGMEM objects)

### 2b. Volatile flags (`ECVF_*`) reported in GS response field 4

| Flag constant | Bit mask | Set when |
|--------------|----------|---------|
| `ECVF_HARD_FAULT` | `0x0002` | In a non-auto-resettable fault state |
| `ECVF_NOGND_TRIPPED` | `0x0020` | No-ground fault has tripped at least once since boot |
| `ECVF_CHARGING_ON` | `0x0040` | Charging relay is currently closed |
| `ECVF_GFI_TRIPPED` | `0x0080` | GFI has tripped at least once since boot |
| `ECVF_EV_CONNECTED` | `0x0100` | EV is connected (valid when pilot ≠ N12) |
| `ECVF_SESSION_ENDED` | `0x0200` | Session-ended marker (set in default model) |

Source: `firmware/open_evse/J1772EvseController.h`

### 2c. Debounce timing constants

| Constant | Value | Source |
|----------|-------|--------|
| `DELAY_STATE_TRANSITION_MS` | 250 ms | `firmware/open_evse/open_evse.h:587` |
| `DELAY_STATE_TRANSITION_A_MS` | 25 ms | `firmware/open_evse/open_evse.h:590` |

The simulator stores these as informational attributes on `EvseStateEngine`
but does not enforce real-time debounce (see simplifications below).

---

## 3. Known Intentional Simplifications

These simplifications are deliberate MVP trade-offs.  They are tracked here so
that future work can reduce the gap with production firmware behavior.

| No. | Simplification | Firmware behavior | Simulator behavior | Impact |
|---|---------------|------------------|--------------------|--------|
| 1 | Debounce timing not enforced | State transitions require the pilot voltage to be stable for `DELAY_STATE_TRANSITION_MS` (250 ms) before the controller changes state | `EvseStateEngine` transitions immediately; timing constants are present as attributes only | ESP sees instant state changes; timing-sensitive retry loops may behave differently |
| 2 | No per-phase or real-time current measurement | Ammeter samples current continuously; `GetChargingCurrent()` returns mA | Simulator has no ammeter model; `GC` reports setpoint only | ESP ammeter polling will see static values |
| 3 | `SC V` (volatile flag) ignored | `SC <amps> V` sets current without persisting to EEPROM | Simulator ignores the `V` suffix | Behavior is identical in MVP since simulator has no EEPROM persistence |
| 4 | `SL A` (auto-detect) not implemented | `SL A` selects service level automatically based on ADVPWR readings | Simulator returns `$NK` for `SL A` | ESP must use `SL 1` or `SL 2` explicitly |
| 5 | GFI / NO_GROUND auto-retry not simulated | Firmware retries fault tests up to `GFI_RETRY_COUNT` times with `GFI_TIMEOUT` interval | Fault stays set until `clear_fault()` is called explicitly | ESP retry-count polling (`GS` field 2 after fault) will not count down |
| 6 | No KWH / energy meter | Firmware accumulates Wh and reports via `$GU` | `$GU` not in MVP command set | ESP energy-display flows not testable in MVP |
| 7 | `EVSE_STATE_D` treated as fault boundary | `EVSE_STATE_D` (0x04) is the first state in the fault range; `_is_fault_state()` returns `True` for it | Same | Matches firmware `InFaultState()` semantics |
| 8 | Non-volatile flags (`ECF_*`) in `GE` always zero | Firmware persists settings to EEPROM and reflects them in `flags` | `EvseModel.flags` defaults to `0x0000` and is not written to EEPROM | ESP settings-read flows will always see default flags |
| 9 | SLEEPING color is WHITE only when `ECVF_EV_CONNECTED` set | `main.cpp:757`: `LcdSetBacklightColor(EvConnected() ? WHITE : VIOLET)` | `DisplayModel.update_from_evse_state()` checks `ECVF_EV_CONNECTED` bit | Matches firmware logic |
| 10 | Auth-lock `TEAL` override not simulated | When `AUTH_LOCK` is enabled and the auth lock is on, states A and B show TEAL instead of GREEN/YELLOW | Simulator always uses GREEN (A) and YELLOW (B) | `AUTH_LOCK` is an optional firmware feature not required for basic ESP debugging |
