"""Tests for Step 4 UART transport (UartTransport).

Uses unittest.mock to avoid requiring a physical serial port.  Verifies
that the transport initialises with firmware-derived defaults, delegates
correctly to the stream parser, and enforces the closed-port guard.
"""

import unittest
from unittest.mock import MagicMock, patch

from open_evse_controller_sim.transport_uart import SERIAL_BAUD, UartTransport


class TestUartTransportDefaults(unittest.TestCase):
    def test_default_baudrate_matches_firmware(self) -> None:
        t = UartTransport("/dev/ttyUSB0")
        self.assertEqual(t.baudrate, SERIAL_BAUD)
        self.assertEqual(SERIAL_BAUD, 115200)

    def test_port_stored(self) -> None:
        t = UartTransport("/dev/ttyS0", baudrate=9600)
        self.assertEqual(t.port, "/dev/ttyS0")
        self.assertEqual(t.baudrate, 9600)

    def test_not_open_initially(self) -> None:
        t = UartTransport("/dev/ttyUSB0")
        self.assertIsNone(t._conn)


class TestUartTransportGuards(unittest.TestCase):
    """Operations must raise RuntimeError when port is not open."""

    def test_send_frame_raises_when_closed(self) -> None:
        t = UartTransport("/dev/ttyUSB0")
        with self.assertRaises(RuntimeError):
            t.send_frame("$GS\r")

    def test_recv_frames_raises_when_closed(self) -> None:
        t = UartTransport("/dev/ttyUSB0")
        with self.assertRaises(RuntimeError):
            t.recv_frames()


class TestUartTransportSerial(unittest.TestCase):
    """Verify serial.Serial is opened with correct 8N1 settings."""

    def _make_mock_serial(self) -> MagicMock:
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_serial.in_waiting = 0
        return mock_serial

    def test_open_uses_correct_settings(self) -> None:
        mock_serial_cls = MagicMock(return_value=self._make_mock_serial())
        with patch("serial.Serial", mock_serial_cls):
            t = UartTransport("/dev/ttyUSB0")
            t.open()
        mock_serial_cls.assert_called_once_with(
            port="/dev/ttyUSB0",
            baudrate=115200,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=0,
        )

    def test_send_frame_encodes_latin1(self) -> None:
        mock_conn = self._make_mock_serial()
        t = UartTransport("/dev/ttyUSB0")
        t._conn = mock_conn
        t.send_frame("$GS^32\r")
        mock_conn.write.assert_called_once_with(b"$GS^32\r")

    def test_recv_frames_feeds_parser(self) -> None:
        mock_conn = self._make_mock_serial()
        mock_conn.in_waiting = len(b"$GV^35\r")
        mock_conn.read.return_value = b"$GV^35\r"
        t = UartTransport("/dev/ttyUSB0")
        t._conn = mock_conn
        frames = t.recv_frames()
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].token, "GV")

    def test_recv_frames_returns_empty_when_no_data(self) -> None:
        mock_conn = self._make_mock_serial()
        mock_conn.in_waiting = 0
        t = UartTransport("/dev/ttyUSB0")
        t._conn = mock_conn
        self.assertEqual(t.recv_frames(), [])

    def test_close_clears_conn(self) -> None:
        mock_conn = self._make_mock_serial()
        t = UartTransport("/dev/ttyUSB0")
        t._conn = mock_conn
        t.close()
        mock_conn.close.assert_called_once()
        self.assertIsNone(t._conn)

    def test_context_manager_opens_and_closes(self) -> None:
        mock_conn = self._make_mock_serial()
        mock_serial_cls = MagicMock(return_value=mock_conn)
        with patch("serial.Serial", mock_serial_cls):
            with UartTransport("/dev/ttyUSB0") as t:
                self.assertIsNotNone(t._conn)
        mock_conn.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
