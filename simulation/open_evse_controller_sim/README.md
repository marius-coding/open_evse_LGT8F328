# OpenEVSE Controller Simulator

Python simulator for OpenEVSE AVR controller behavior over UART/RAPI.

## Scope (MVP)

- Strict RAPI framing/parser behavior (`$...\r`, checksums, sequence IDs)
- Command set: `GV`, `GS`, `GE`, `GC`, `G0`, `SC`, `FE`, `FD`, `SL`
- Async notifications: `AB` (boot), `AT` (state change)
- EVSE state engine for A/B/C, enabled/disabled/sleeping, and major fault states
- Display state model for firmware-like 16x2 text/color mapping

## Install

From the repository root:

```bash
python -m pip install pyserial
```

Optional GUI support:

```bash
python -m pip install dearpygui
```

build_gui()

## Run the simulator (GUI by default)

From the repository root:

```bash
PYTHONPATH=simulation python -m open_evse_controller_sim
```

This launches the display simulation GUI. Requires `dearpygui` (see Install).

The GUI is interactive and includes:

- live EV/operator controls (vehicle connected/charging state, current, service level, enable/disable/sleep)
- fault injection controls (GFI, no-ground, stuck-relay, diode, clear fault)
- optional live serial connection to an ESP target
- RAPI traffic monitor showing RX/TX frames in real time

To auto-connect the GUI to a serial device on startup:

```bash
PYTHONPATH=simulation python -m open_evse_controller_sim --port /dev/ttyUSB0
```

## UART protocol (headless) mode

To run the simulator as a UART protocol endpoint for ESP debugging:

```bash
PYTHONPATH=simulation python -m open_evse_controller_sim --headless --port /dev/ttyUSB0
```

Options:

- `--baudrate 115200` (default from firmware)
- `--poll-interval-ms 10`
- `--no-boot-notify` (disables startup `AB`)
- `--once` (single poll iteration)

## Run display GUI from Python

```python
from open_evse_controller_sim.gui import build_gui
build_gui()

# Optional live serial connection
build_gui(port="/dev/ttyUSB0")
```

## Run tests

```bash
pytest -q simulation/open_evse_controller_sim/test_vectors
```
