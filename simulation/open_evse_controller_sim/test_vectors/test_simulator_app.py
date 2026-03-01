"""Tests for simulator runtime loop and CLI glue."""

from __future__ import annotations

import unittest

from open_evse_controller_sim.evse_model import EvseModel
from open_evse_controller_sim.rapi_dispatch import RapiDispatcher
from open_evse_controller_sim.rapi_parser import ParsedRapiFrame, parse_frame
from open_evse_controller_sim.simulator_app import SimulatorApp, _parse_args


class _FakeTransport:
    def __init__(self, incoming_raw: list[str] | None = None) -> None:
        self.incoming_raw = incoming_raw[:] if incoming_raw else []
        self.outgoing: list[str] = []

    def recv_frames(self) -> list[ParsedRapiFrame]:
        parsed: list[ParsedRapiFrame] = []
        while self.incoming_raw:
            raw = self.incoming_raw.pop(0)
            frame = parse_frame(raw)
            if frame is not None:
                parsed.append(frame)
        return parsed

    def send_frame(self, frame: str) -> None:
        self.outgoing.append(frame)


class TestSimulatorAppBootNotification(unittest.TestCase):
    def test_boot_notification_sent_once(self) -> None:
        transport = _FakeTransport()
        app = SimulatorApp(transport)

        app.process_once()
        app.process_once()

        self.assertEqual(len(transport.outgoing), 1)
        self.assertTrue(transport.outgoing[0].startswith("$AB "))

    def test_boot_notification_can_be_disabled(self) -> None:
        transport = _FakeTransport()
        app = SimulatorApp(transport, send_boot_notification=False)

        app.process_once()

        self.assertEqual(transport.outgoing, [])


class TestSimulatorAppDispatchLoop(unittest.TestCase):
    def test_dispatches_commands_and_writes_response(self) -> None:
        transport = _FakeTransport(incoming_raw=["$GV\r"])
        app = SimulatorApp(transport, send_boot_notification=False)

        processed = app.process_once()

        self.assertEqual(processed, 1)
        self.assertEqual(len(transport.outgoing), 1)
        self.assertTrue(transport.outgoing[0].startswith("$OK 8.2.3 5.2.1-LGT"))

    def test_state_change_emits_at_notification(self) -> None:
        model = EvseModel(evse_state=0x01, enabled=True)
        dispatcher = RapiDispatcher(model)
        transport = _FakeTransport(incoming_raw=["$FD\r"])
        app = SimulatorApp(transport, dispatcher, send_boot_notification=False)

        app.process_once()

        self.assertEqual(len(transport.outgoing), 2)
        self.assertTrue(transport.outgoing[0].startswith("$OK"))
        self.assertTrue(transport.outgoing[1].startswith("$AT "))

    def test_no_state_change_does_not_emit_at(self) -> None:
        model = EvseModel(evse_state=0x01)
        dispatcher = RapiDispatcher(model)
        transport = _FakeTransport(incoming_raw=["$GS\r"])
        app = SimulatorApp(transport, dispatcher, send_boot_notification=False)

        app.process_once()

        self.assertEqual(len(transport.outgoing), 1)
        self.assertTrue(transport.outgoing[0].startswith("$OK 01"))


class TestCliArgumentParsing(unittest.TestCase):
    def test_required_port(self) -> None:
        args = _parse_args(["--port", "/dev/ttyUSB0"])
        self.assertEqual(args.port, "/dev/ttyUSB0")
        self.assertEqual(args.baudrate, 115200)

    def test_once_flag(self) -> None:
        args = _parse_args(["--port", "/dev/ttyUSB0", "--once"])
        self.assertTrue(args.once)

    def test_disable_boot_notification_flag(self) -> None:
        args = _parse_args(["--port", "/dev/ttyUSB0", "--no-boot-notify"])
        self.assertTrue(args.no_boot_notify)


if __name__ == "__main__":
    unittest.main()
