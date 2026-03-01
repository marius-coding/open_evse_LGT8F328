"""Step 4: UART transport for OpenEVSE RAPI protocol.

Firmware reference:
  - Baud rate : SERIAL_BAUD 115200   (firmware/open_evse/open_evse.h:532)
  - Setup call: Serial.begin(SERIAL_BAUD) (firmware/open_evse/main.cpp:2479)
  - Frame format: 8N1 (8 data bits, no parity, 1 stop bit) – FTDI-compatible
    USB–serial default matching AVR hardware UART defaults.

Runtime dependency note:
  ``pyserial`` is imported lazily inside :meth:`UartTransport.open` so this
  module can be imported (e.g. in tests using mocks) without pyserial present.
  Install it with ``pip install pyserial`` before calling ``open()``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .rapi_parser import ParsedRapiFrame, RapiStreamParser

if TYPE_CHECKING:
    import serial as _serial

# Firmware default baud rate (open_evse.h: #define SERIAL_BAUD 115200)
SERIAL_BAUD = 115200

# FTDI-compatible 8N1 framing matching AVR UART hardware defaults
_BYTESIZE = 8
_PARITY = "N"
_STOPBITS = 1


class UartTransport:
    """FTDI-compatible UART transport for RAPI framed communication.

    Usage::

        with UartTransport("/dev/ttyUSB0") as t:
            t.send_frame("$GS^32\\r")
            frames = t.recv_frames()
    """

    def __init__(self, port: str, baudrate: int = SERIAL_BAUD) -> None:
        self.port = port
        self.baudrate = baudrate
        self._conn: Optional[_serial.Serial] = None
        self._parser = RapiStreamParser()

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Open the serial port with FTDI-compatible 8N1 settings."""
        import serial  # lazy import keeps module usable without pyserial installed

        self._conn = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=_BYTESIZE,
            parity=_PARITY,
            stopbits=_STOPBITS,
            timeout=0,  # non-blocking read
        )

    def close(self) -> None:
        """Close the serial port if open."""
        if self._conn is not None and self._conn.is_open:
            self._conn.close()
        self._conn = None

    def __enter__(self) -> "UartTransport":
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    def send_frame(self, frame: str) -> None:
        """Write one RAPI frame to the serial port.

        The string is encoded as Latin-1, which is a safe superset of ASCII
        and matches the AVR firmware's byte-level representation.
        """
        if self._conn is None or not self._conn.is_open:
            raise RuntimeError("Transport is not open")
        self._conn.write(frame.encode("latin-1"))

    def recv_frames(self) -> list[ParsedRapiFrame]:
        """Read all available bytes and return any complete RAPI frames.

        Uses the internal RapiStreamParser so partial frames are buffered
        across calls, mirroring EvseRapiProcessor::doCmd() incremental
        character processing.
        """
        if self._conn is None or not self._conn.is_open:
            raise RuntimeError("Transport is not open")
        pending = self._conn.in_waiting
        if not pending:
            return []
        raw = self._conn.read(pending)
        return self._parser.feed(raw.decode("latin-1"))

