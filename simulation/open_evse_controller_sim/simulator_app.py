"""Runtime simulator application for OpenEVSE UART/RAPI interoperability.

This module wires the transport, parser output, and dispatcher into a simple
poll-loop service that can be connected directly to an ESP over serial.
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from typing import Callable, Protocol

from .evse_model import EvseModel
from .rapi_dispatch import RapiDispatcher
from .rapi_parser import ParsedRapiFrame
from .transport_uart import SERIAL_BAUD, UartTransport


class TransportProtocol(Protocol):
    def send_frame(self, frame: str) -> None:
        ...

    def recv_frames(self) -> list[ParsedRapiFrame]:
        ...


@dataclass(frozen=True)
class _StateSnapshot:
    evse_state: int
    pilot_state: int
    current_capacity_amps: int
    vflags: int


class SimulatorApp:
    """Serial poll-loop simulator runtime.

    Responsibilities:
    - send optional startup boot notification (`AB`)
    - process incoming RAPI command frames and write responses
    - emit `AT` notifications when state fields change
    """

    def __init__(
        self,
        transport: TransportProtocol,
        dispatcher: RapiDispatcher | None = None,
        *,
        send_boot_notification: bool = True,
        traffic_hook: Callable[[str, str], None] | None = None,
    ) -> None:
        self._transport = transport
        self._dispatcher = dispatcher if dispatcher is not None else RapiDispatcher(EvseModel())
        self._send_boot_notification = send_boot_notification
        self._traffic_hook = traffic_hook
        self._last_state = self._snapshot()
        self._boot_sent = False

    @property
    def dispatcher(self) -> RapiDispatcher:
        return self._dispatcher

    def _snapshot(self) -> _StateSnapshot:
        model = self._dispatcher.model
        return _StateSnapshot(
            evse_state=model.evse_state,
            pilot_state=model.pilot_state,
            current_capacity_amps=model.current_capacity_amps,
            vflags=model.vflags,
        )

    def _send_boot_once(self) -> None:
        if self._send_boot_notification and not self._boot_sent:
            self._send(self._dispatcher.build_boot_notification())
            self._boot_sent = True

    def _emit_traffic(self, direction: str, frame: str) -> None:
        if self._traffic_hook is not None:
            self._traffic_hook(direction, frame)

    def _send(self, frame: str) -> None:
        self._transport.send_frame(frame)
        self._emit_traffic("tx", frame)

    def notify_state_if_changed(self, *, force: bool = False) -> bool:
        """Send AT notification if model state changed.

        Args:
            force: When True, always send a state notification.

        Returns:
            True if an AT notification was sent.
        """
        new_state = self._snapshot()
        if force or new_state != self._last_state:
            self._send(self._dispatcher.build_state_notification())
            self._last_state = self._snapshot()
            return True
        self._last_state = new_state
        return False

    def process_once(self) -> int:
        """Process one poll iteration.

        Returns:
            Number of incoming command frames processed.
        """
        self._send_boot_once()
        frames = self._transport.recv_frames()
        for frame in frames:
            self._emit_traffic("rx", frame.raw)
            response = self._dispatcher.dispatch(frame)
            self._send(response)
            self.notify_state_if_changed()

        return len(frames)

    def run_forever(self, poll_interval_s: float = 0.01) -> None:
        """Run until interrupted."""
        self._send_boot_once()
        while True:
            self.process_once()
            if poll_interval_s > 0:
                time.sleep(poll_interval_s)



def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OpenEVSE controller simulator runtime. By default, launches interactive GUI mode. Use --headless for UART-only mode.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run in UART protocol mode only (no GUI)",
    )
    parser.add_argument(
        "--port",
        help="Serial port, e.g. /dev/ttyUSB0 (optional in GUI mode, required in headless mode)",
    )
    parser.add_argument(
        "--baudrate",
        type=int,
        default=SERIAL_BAUD,
        help=f"UART baud rate (default: {SERIAL_BAUD})",
    )
    parser.add_argument(
        "--poll-interval-ms",
        type=float,
        default=10.0,
        help="Polling interval in milliseconds (default: 10)",
    )
    parser.add_argument(
        "--no-boot-notify",
        action="store_true",
        help="Do not emit startup AB notification",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process one poll iteration and exit (headless mode only)",
    )
    return parser.parse_args(argv)



def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not args.headless:
        # Default: launch the GUI
        try:
            from .gui import build_gui
        except ImportError:
            print("DearPyGui is required for GUI mode. Install with: pip install dearpygui", flush=True)
            return 1
        build_gui(
            port=args.port,
            baudrate=args.baudrate,
            send_boot_notification=not args.no_boot_notify,
        )
        return 0

    # Headless UART protocol mode
    if not args.port:
        print("--port is required in headless mode.", flush=True)
        return 2
    transport = UartTransport(port=args.port, baudrate=args.baudrate)
    app = SimulatorApp(
        transport,
        send_boot_notification=not args.no_boot_notify,
    )

    with transport:
        if args.once:
            app.process_once()
            return 0

        try:
            app.run_forever(max(args.poll_interval_ms, 0.0) / 1000.0)
        except KeyboardInterrupt:
            return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
