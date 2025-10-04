
## Kinetos (LGT8F328) fork

This repository is a fork of the original OpenEVSE firmware modified to support Kinetos wallboxes which use a different MCU and a few hardware differences.

Summary of changes vs upstream OpenEVSE
- MCU: replaced ATmega328P with LGT8F328P (LGT8FX family).
- Programming: can be programmed using a LGT8F328-based Arduino board running the LarduinoISP firmware.
- Peripheral changes: Kinetos uses an LM75B style temperature sensor ("75B") in places where some OpenEVSE variants use an TMP007
- GFI (RCD) test: the GFI device on Kinetos boards does not trigger reliably via the PCB test input; use the wire-loop workaround described below.

How to build and flash (Arduino IDE)
1. In the Arduino IDE, open File → Preferences → Additional Boards Manager URLs and add:

	https://raw.githubusercontent.com/dbuezas/lgt8fx/master/package_lgt8fx_index.json

	then open Tools → Boards → Boards Manager and install the LGT package.

2. Flash the `LarduinoISP` example to a spare Arduino (this will act as the ISP programmer for the Kinetos board).

3. Connect the Arduino to the Kinetos board using the connector marked "SWC, RST, SWD" . Wiring used for programming:

	- slave reset: Arduino D10 -> Kinetos PC6 / RESET
	- SWD (data):  Arduino D12 -> Kinetos PE2 / SWD
	- SWC (clock): Arduino D13 -> Kinetos PE0 / SCK

	Note: These pin names match the usual Arduino-pin numbering for the `LarduinoISP` sketch. Double-check your board silk-screen and the `LarduinoISP` wiring before powering anything.

4. Open `firmware/open_evse/open_evse.ino` in the Arduino IDE and compile. The Arduino IDE writes the generated .hex file to a temporary build folder (location depends on OS and IDE version). Note the path reported by the IDE after compilation.

5. Use avrdude to flash the final .hex to the LGT8F328P. Example command (replace COMPORT and test.hex with your serial port):

	avrdude -p lgt8f328p -c avrisp -P COMPORT -b 115200 -U flash:w:open_evse.ino.hex:i

	On Linux the COMPORT will look like `/dev/ttyUSB0` or similar. On Windows use `COM3` style names.

    don't use open_evse.ino.with_bootloader.hex. (Have tried it, didn't work)

GFI (RCD) self-test workaround
- The Kinetos GFI (RCD) test input does not reliably trigger the built-in self-test on all hardware revisions. Instead, use the following safe test method:
  1. Create a wire loop and pass it twice through the toroidal current transformer (toroid).
  2. Connect one end of the loop to ground and the other end to the PCB's "Test" output.
  3. Provide a pull-up from the Test output to 5V (470Ω recommended). The Test output is an open-collector output and requires a pull-up to drive high.

Safety and notes
- This firmware controls mains-connected hardware. Only perform flashing and GFI tests if you are qualified and follow proper safety procedures. Disconnect mains power when wiring or making hardware changes.
- Do not remove or weaken safety checks (GFI, stuck-relay protection, etc.) — they are present for user safety.
 - Disclaimer: This firmware is experimental and may not be safe. Use at your own risk. The authors and maintainers accept no liability for damage, injury, or loss resulting from use of this code.


# OpenEVSE

Firmware for OpenEVSE controller used in OpenEVSE Charging Stations sold in the USA, and OpenEnergyMonitor EmonEVSE units sold in (UK/EU).

- OpenEVSE: <https://store.openevse.com/collections/all-products>
- EmonEVSE: <https://shop.openenergymonitor.com/evse/>

Based on OpenEVSE: Open Source Hardware J1772 Electric Vehicle Supply Equipment

## USA

TODO: add notes about USA OpenEVSE

## UK/EU

- Disable `AUTOSVCLEVEL` (autodetection is designed for split-phase)
- Charging level default to `L2`
- Set `MAX_CURRENT_CAPACITY_L2 32` (limit for single-phase charging in UK/EU)
- Add '.EU' to version number
- Enable LCD Redraw every couple of min (required for EMC/CE)

### EmonEVSE

EmonEVSE (non-tethered type-2 EVSE unit)

- `PP_AUTO_AMPACITY` enabled to set max current based on non-tethered cable connected
- Three-phase option with `THREEPHASE` enabled to calculate three-phase energy ( Unneeded with ESP32_WiFi firmware >= 4.2

## API Documentation

- WIFI API: <http://github.com/openevse/ESP32_WiFi_V4.x/>
- RAPI API: <https://github.com/openenergymonitor/open_evse/blob/master/firmware/open_evse/rapi_proc.h>

## Resources

- [OpenEnergyMonitor OpenEVSE Setup Guide](https://guide.openenergymonitor.org/integrations/openevse)
- [OpenEnergyMonitor OpenEVSE Shop](https://shop.openenergymonitor.com/ev-charging/)

- [OpenEVSE Controller Datasheet](https://github.com/OpenEVSE/OpenEVSE_PLUS/blob/master/OpenEVSE_PLUS_v5/OpenEVSE_Plus_v5.pdf)
- [OpenEVSE Controller Hardware Repo](https://github.com/OpenEVSE/OpenEVSE_PLUS)
- [OpenEVSE Project Homepage](https://openevse.com)

***

Firmware compile & upload help: [firmware/open_evse/LoadingFirmware.md](firmware/open_evse/LoadingFirmware.md)

NOTES:

- Working versions of the required libraries are included with the firmware code. This avoids potential issues related to using the wrong versions of the libraries.
- Highly recommend using the tested pre-compiled firmware (see releases page)

```text
Open EVSE is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 3, or (at your option)
any later version.

Open EVSE is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Open EVSE; see the file COPYING.  If not, write to the
Free Software Foundation, Inc., 59 Temple Place - Suite 330,
Boston, MA 02111-1307, USA.

* Open EVSE is distributed in the hope that it will be useful,
* but WITHOUT ANY WARRANTY; without even the implied warranty of
* MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
```
