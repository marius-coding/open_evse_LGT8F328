## Plan: OpenEVSE Controller Simulator (DRAFT)

Build a Python desktop simulator (DearPyGui) that emulates the OpenEVSE controller over UART/RAPI so the ESP can be debugged without AVR hardware. The first milestone prioritizes strict protocol compatibility (framing, checksum, sequence handling, response style, async notifications), then adds a simple but realistic EVSE state model (A/B/C + enable/disable + charging), display simulation (text + color), and operator fault injection controls. Research is treated as a first-class workstream: we will extract firmware behavior from the actual AVR sources and convert it into executable simulator rules plus compatibility tests, so the ESP sees controller behavior that is close to production firmware.

**Steps**
1. Define the simulator behavior contract from firmware sources and freeze an MVP command/event matrix based on [firmware/open_evse/rapi_proc.h](firmware/open_evse/rapi_proc.h), [firmware/open_evse/rapi_proc.cpp](firmware/open_evse/rapi_proc.cpp), [firmware/open_evse/J1772EvseController.h](firmware/open_evse/J1772EvseController.h), and [firmware/open_evse/J1772EvseController.cpp](firmware/open_evse/J1772EvseController.cpp).
2. Create a dedicated simulator workspace (separate from firmware tree) with clear modules: `transport_uart`, `rapi_parser`, `rapi_dispatch`, `evse_model`, `fault_model`, `display_model`, `gui`, and `test_vectors`.
3. Implement strict RAPI framing/parsing/serialization to mirror firmware behavior of `EvseRapiProcessor::doCmd`, `EvseRapiProcessor::response`, and checksum/seq-id conventions documented in [firmware/open_evse/rapi_proc.h](firmware/open_evse/rapi_proc.h) and implemented in [firmware/open_evse/rapi_proc.cpp](firmware/open_evse/rapi_proc.cpp#L109-L241).
4. Implement UART transport using FTDI-compatible serial settings aligned with firmware defaults from [firmware/open_evse/open_evse.h](firmware/open_evse/open_evse.h#L532) and setup behavior seen in [firmware/open_evse/main.cpp](firmware/open_evse/main.cpp#L2479-L2481).
5. Implement RAPI command handlers required for ESP debugging first: `GV`, `GS`, `GE`, `GC`, `G0`, `SC`, `FE`, `FD`, `SL`, and include async `AB` + `AT` notifications matching payload formats from [firmware/open_evse/rapi_proc.cpp](firmware/open_evse/rapi_proc.cpp#L151-L190) and [firmware/open_evse/rapi_proc.cpp](firmware/open_evse/rapi_proc.cpp#L602-L803).
6. Build a minimal EVSE state engine that mirrors core transitions (A/B/C, disabled, sleeping, fault placeholders) and debounce/timing intent from [firmware/open_evse/J1772EvseController.cpp](firmware/open_evse/J1772EvseController.cpp#L1253-L1601) plus constants in [firmware/open_evse/open_evse.h](firmware/open_evse/open_evse.h#L587-L590).
7. Add operator controls for “vehicle response” abstraction (state/pilot interpretation), charge current setpoint, and enabled/disabled mode; map controls to the same fields the RAPI responses use so `GS/GE/GC` remain coherent.
8. Add fault injection panel (GFI/ground/stuck-relay/diode fault simulation) as state flags and transitions only; do not emulate low-level analog circuitry in MVP. Align fault naming and semantics with logic visible in [firmware/open_evse/J1772EvseController.cpp](firmware/open_evse/J1772EvseController.cpp#L1348-L1510).
9. Implement display simulation widget driven by state, reusing firmware text/color intent from [firmware/open_evse/main.cpp](firmware/open_evse/main.cpp#L506-L980), color constants in [firmware/open_evse/open_evse.h](firmware/open_evse/open_evse.h#L640-L646), and strings from [firmware/open_evse/strings.h](firmware/open_evse/strings.h).
10. Add a “firmware behavior research pack” in docs: command compatibility table, state mapping table, and known intentional simplifications, with source anchors to [README.md](README.md), [firmware/open_evse/LoadingFirmware.md](firmware/open_evse/LoadingFirmware.md), and relevant source files above.
11. Add deterministic protocol tests using captured command/response vectors (including bad checksum and sequence-id cases) and simulator integration tests over a loopback/virtual serial port.
12. Run end-to-end ESP debug trials: connect ESP to simulator UART, validate startup handshake, periodic polling, command writes, and async event handling; then iterate on mismatches before expanding command coverage.

**Verification**
- Protocol conformance: automated tests for framing, checksum, sequence echo, `$OK/$NK` response forms, and async packet formats.
- Behavioral conformance: state-transition tests for A/B/C + enable/disable + selected faults, including timing/debounce tolerance bands.
- ESP interoperability: scripted session replay of expected ESP command flows against simulator UART.
- Regression gate: each change must pass protocol tests and one full ESP handshake scenario before merge.

**Decisions**
- UI framework: DearPyGui.
- Compatibility mode: strict RAPI protocol compatibility.
- MVP includes: UART RAPI core, simple EV model, display text/color simulation, fault injection controls.
- Current measurement scope: simulator will not model per-phase or ESP-side current measurement in MVP.
- Boundary: emulate controller behavior at protocol/state level first; defer deep hardware-analog fidelity and nonessential feature flags until interoperability is stable.
