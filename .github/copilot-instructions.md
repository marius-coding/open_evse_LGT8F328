This file gives concise, repo-specific guidance for AI coding agents working on the OpenEVSE AVR firmware.

Keep it short and actionable. When in doubt, prefer minimal, low-risk changes and include tests or a quick smoke validation.

1) Big picture (what this repo is)
- Firmware for OpenEVSE / EmonEVSE AVR-based controllers (ATmega328P) in `firmware/open_evse`.
- Main components: core firmware entrypoints (`open_evse.ino` / `main.cpp`), controller logic (`J1772EvseController.*`), hardware interfaces (LCD, pilot, GFI, ammeter), and the RAPI protocol (`rapi_proc.*`).
- Builds use PlatformIO (see `platformio.ini`) or classic avr tools/avrdude for factory flashing.

2) Typical developer workflows (commands & scripts)
- Fast build (PlatformIO): run in repo root with PlatformIO installed:
  - Build: `pio run` (uses `firmware/open_evse` as src dir)
  - Upload (program via ISP/usbasp): `pio run -t program`
- Precompiled hex / factory flashing with avrdude:
  - Set fuses (factory): `./factory_upload.sh` (calls `avrdude`); contents shown in repo root.
  - Direct flash example from README: `avrdude -p atmega328p -B6 -c usbasp -P usb -e -U flash:w:firmware.hex`
- CI: GitHub Actions build is present in `.github/workflows/build_arduino.yml`. Use it as canonical build flags and artifact locations.

3) Project-specific conventions & patterns
- Feature flags are controlled with #defines in code and via PlatformIO build_flags in `platformio.ini` (e.g. `-D RAPI`, `-D AMMETER`). When adding features, follow the existing pattern: guard code with #ifdef and update `platformio.ini` as appropriate.
- Firmware versioning: VERSION defined in `open_evse.h` and `platformio.ini` uses a common.version string. CI extracts version from `open_evse.h`.
- I/O initialization for shared libs: several libraries (Wire, LiquidTWI2, etc.) are intentionally initialized from `open_evse.ino`/`main.cpp` — avoid duplicating `Wire.begin()` in other modules.
- EEPROM / persistent settings: many commands write straight to EEPROM. When changing behavior, search for `eeprom_write_byte` and related helpers.

4) RAPI protocol & integration points
- The RAPI protocol implementation lives in `firmware/open_evse/rapi_proc.h` and `rapi_proc.cpp`.
- RAPI supports serial and I2C transports via `RAPI_SERIAL` and `RAPI_I2C` build flags. Look at the `EvseSerialRapiProcessor` and `EvseI2cRapiProcessor` classes for IO hooks.
- When adding commands, follow tokenization and checksum rules in `rapi_proc.*`. Add handling in `EvseRapiProcessor::processCmd()` and update any callers that use `RapiSendEvseState()`.
- Examples: get state `$GS`, set current `$SC amps`, boot notification `$AB` — see `rapi_proc.h` comments for canonical formats and `rapi_proc.cpp` for concrete implementations.

5) Testing and safety
- This is firmware for mains-connected hardware. Never suggest code that reduces safety checks by default (GFI, ground checks, stuck-relay protection). Changes that affect safety flags must include a clear rationale and preferably a test plan.
- Prefer non-invasive tests: unit-level refactors, small helper functions, compile-only CI validation. When adding runtime tests, provide instructions for safe test harnessing (simulate via #defines like `FAKE_CHARGING_CURRENT` or test-only RAPI commands guarded by `RAPI_T_COMMANDS`).

6) File pointers worth referencing in suggestions
- `firmware/open_evse/main.cpp` - main loop, display, menus, and high-level flow.
- `firmware/open_evse/open_evse.h` / `open_evse.ino` - central defines, configuration, and wiring patterns.
- `firmware/open_evse/rapi_proc.h` / `rapi_proc.cpp` - RAPI parsing, checksum rules, and commands.
- `platformio.ini` - build flags and environment matrix (US vs EU variants).
- `firmware/open_evse/LoadingFirmware.md` and `README.md` - build & flash instructions used by humans; mirror these in scripts or CI if you automate.

7) Small guidelines for PRs by an AI agent
- Keep changes small and well-scoped. Prefer compile-only changes first. Run `pio run` and reference CI workflow for matching flags.
- Update `CHANGELOG` or add a short note in the commit message when altering behavior that affects hardware safety or EEPROM layout.
- If adding new RAPI commands, include unit-like examples (the exact command string and expected response) in the PR description.

If anything in this file is unclear or you need more examples (tests, example RAPI exchanges, or a safety checklist), ask for the specific area and I will extend this doc.
