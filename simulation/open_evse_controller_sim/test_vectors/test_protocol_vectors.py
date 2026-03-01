"""Step 11: Deterministic protocol tests.

Captured command/response vectors with exact expected strings, bad-checksum
rejection tests, sequence-id echo tests, and a loopback integration test that
exercises the full stack (UartTransport → RapiStreamParser → RapiDispatcher →
response serialisation → re-parse) without real serial hardware.

All checksum values were computed from the reference XOR algorithm in
rapi_parser._checksum_xor(), cross-checked against firmware behavior.
"""

import io
import unittest

from open_evse_controller_sim.evse_model import (
    ECVF_EV_CONNECTED,
    EVSE_STATE_A,
    EVSE_STATE_DISABLED,
    EvseModel,
)
from open_evse_controller_sim.rapi_dispatch import RapiDispatcher
from open_evse_controller_sim.rapi_parser import (
    RapiStreamParser,
    parse_frame,
)
from open_evse_controller_sim.transport_uart import UartTransport


# ---------------------------------------------------------------------------
# Deterministic command/response vector table
# Format: (raw_command_frame, expected_response_frame)
# Checksums pre-computed from _checksum_xor for the default EvseModel.
# ---------------------------------------------------------------------------

# Default EvseModel values used for GET command vectors:
#   evse_state=0x01, elapsed=0, pilot=0x00, vflags=0x0200
#   current_capacity_amps=16, flags=0x0000, svc_level=2, max_hw_current_capacity=32

_CMD_RESPONSE_VECTORS: list[tuple[str, str]] = [
    # GV – get version
    ("$GV\r",      "$OK 8.2.3 5.2.1-LGT^5D\r"),
    # GS – get state (default model)
    ("$GS\r",      "$OK 01 0 00 0200^13\r"),
    # GE – get settings (default model: 16 A, flags 0x0000)
    ("$GE\r",      "$OK 16 0000^27\r"),
    # GC – get capacity range (L2, hw_max=32, cur=16)
    ("$GC\r",      "$OK 6 32 16 32^11\r"),
    # G0 – connect state: disconnected (default model vflags=0x0200)
    ("$G0\r",      "$OK 0^30\r"),
    # SC – set current to 24 A
    ("$SC 24\r",   "$OK 24^06\r"),
    # FD – disable
    ("$FD\r",      "$OK^20\r"),
    # FE – enable (after FD model is already disabled, FE re-enables → state A)
    ("$FE\r",      "$OK^20\r"),
    # SL – set service level 1
    ("$SL 1\r",    "$OK^20\r"),
    # SL – set service level 2
    ("$SL 2\r",    "$OK^20\r"),
    # Unknown command → NK
    ("$GF\r",      "$NK^21\r"),
    # SC with no args → NK
    ("$SC\r",      "$NK^21\r"),
    # SL with invalid level → NK
    ("$SL 3\r",    "$NK^21\r"),
]


class TestCommandResponseVectors(unittest.TestCase):
    """Deterministic protocol test vectors.

    Each test case dispatches a known command against a freshly-created
    default EvseModel and asserts that the exact response string matches the
    pre-computed expected value.

    For stateful commands (SC, FD, FE, SL) a fresh model is used per-vector
    so that previous mutations do not affect the expected response.
    """

    def _dispatch_raw(self, raw: str, model: EvseModel | None = None) -> str:
        parsed = parse_frame(raw)
        assert parsed is not None, f"parse_frame failed for: {raw!r}"
        d = RapiDispatcher(model if model is not None else EvseModel())
        return d.dispatch(parsed)

    def test_gv_exact_vector(self) -> None:
        self.assertEqual(self._dispatch_raw("$GV\r"), "$OK 8.2.3 5.2.1-LGT^5D\r")

    def test_gs_exact_vector(self) -> None:
        self.assertEqual(self._dispatch_raw("$GS\r"), "$OK 01 0 00 0200^13\r")

    def test_ge_exact_vector(self) -> None:
        self.assertEqual(self._dispatch_raw("$GE\r"), "$OK 16 0000^27\r")

    def test_gc_exact_vector(self) -> None:
        self.assertEqual(self._dispatch_raw("$GC\r"), "$OK 6 32 16 32^11\r")

    def test_g0_exact_vector(self) -> None:
        self.assertEqual(self._dispatch_raw("$G0\r"), "$OK 0^30\r")

    def test_sc_exact_vector(self) -> None:
        self.assertEqual(
            self._dispatch_raw("$SC 24\r", EvseModel(max_hw_current_capacity=32)),
            "$OK 24^06\r",
        )

    def test_fd_exact_vector(self) -> None:
        self.assertEqual(self._dispatch_raw("$FD\r"), "$OK^20\r")

    def test_fe_exact_vector(self) -> None:
        model = EvseModel(enabled=False, evse_state=EVSE_STATE_DISABLED)
        self.assertEqual(self._dispatch_raw("$FE\r", model), "$OK^20\r")

    def test_sl1_exact_vector(self) -> None:
        self.assertEqual(self._dispatch_raw("$SL 1\r"), "$OK^20\r")

    def test_sl2_exact_vector(self) -> None:
        self.assertEqual(self._dispatch_raw("$SL 2\r"), "$OK^20\r")

    def test_unknown_command_exact_nk(self) -> None:
        self.assertEqual(self._dispatch_raw("$GF\r"), "$NK^21\r")

    def test_sc_no_args_exact_nk(self) -> None:
        self.assertEqual(self._dispatch_raw("$SC\r"), "$NK^21\r")

    def test_sl_invalid_level_exact_nk(self) -> None:
        self.assertEqual(self._dispatch_raw("$SL 3\r"), "$NK^21\r")

    def test_all_vectors_produce_valid_frames(self) -> None:
        """Every vector in the table must produce a re-parseable RAPI frame."""
        for cmd, expected in _CMD_RESPONSE_VECTORS:
            with self.subTest(cmd=cmd):
                resp = self._dispatch_raw(cmd)
                self.assertEqual(resp, expected, f"vector mismatch for {cmd!r}")
                self.assertIsNotNone(parse_frame(resp), f"response not parseable: {resp!r}")


# ---------------------------------------------------------------------------
# Bad-checksum test vectors
# ---------------------------------------------------------------------------

class TestBadChecksumRejection(unittest.TestCase):
    """Frames with wrong checksums must be rejected by parse_frame."""

    def test_gv_wrong_xor_checksum(self) -> None:
        # Correct is $GV^35\r; ^00 is deliberately wrong
        self.assertIsNone(parse_frame("$GV^00\r"))

    def test_gs_wrong_xor_checksum(self) -> None:
        # Correct is $GS^30\r; ^FF is wrong
        self.assertIsNone(parse_frame("$GS^FF\r"))

    def test_fd_wrong_additive_checksum(self) -> None:
        # Correct additive is $FD*AE\r; *00 is wrong
        self.assertIsNone(parse_frame("$FD*00\r"))

    def test_sc_with_args_wrong_checksum(self) -> None:
        # Any wrong checksum digit must reject the frame
        self.assertIsNone(parse_frame("$SC 16^00\r"))

    def test_stream_parser_drops_bad_checksum_frames(self) -> None:
        """Bad-checksum frames must not appear in RapiStreamParser output."""
        parser = RapiStreamParser()
        # Mix good ($GV^35\r) and bad ($GS^00\r) frames
        result = parser.feed("$GV^35\r$GS^00\r")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].token, "GV")

    def test_stream_parser_accepts_valid_after_bad(self) -> None:
        """Parser must recover and parse the next valid frame after a bad one."""
        parser = RapiStreamParser()
        result = parser.feed("$GV^00\r$FD*AE\r")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].token, "FD")


# ---------------------------------------------------------------------------
# Sequence-ID echo test vectors
# ---------------------------------------------------------------------------

class TestSequenceIdEcho(unittest.TestCase):
    """Sequence IDs present in the request must be echoed in the response."""

    def _dispatch_raw(self, raw: str, model: EvseModel | None = None) -> str:
        parsed = parse_frame(raw)
        assert parsed is not None
        return RapiDispatcher(model if model is not None else EvseModel()).dispatch(parsed)

    def test_gv_with_seq_7a_echoed_in_response(self) -> None:
        # $GV :7A^59\r is the known-good framed GV command with seq=0x7A
        resp = self._dispatch_raw("$GV :7A^59\r")
        self.assertIn(":7A", resp)
        self.assertTrue(resp.startswith("$OK "))
        # Full vector: $OK 8.2.3 5.2.1-LGT :7A^31\r
        self.assertEqual(resp, "$OK 8.2.3 5.2.1-LGT :7A^31\r")

    def test_gs_with_seq_01_echoed(self) -> None:
        # $GS :01^2B\r is the known-good framed GS command with seq=0x01
        resp = self._dispatch_raw("$GS :01^2B\r")
        self.assertIn(":01", resp)
        # Full vector: $OK 01 0 00 0200 :01^08\r
        self.assertEqual(resp, "$OK 01 0 00 0200 :01^08\r")

    def test_seq_id_in_response_is_parseable(self) -> None:
        resp = self._dispatch_raw("$GV :7A^59\r")
        parsed = parse_frame(resp)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.sequence_id, 0x7A)

    def test_no_seq_id_in_response_when_absent_in_request(self) -> None:
        resp = self._dispatch_raw("$GV\r")
        self.assertNotIn(":", resp.replace("$", "").replace("^", ""))

    def test_nk_response_also_echoes_seq_id(self) -> None:
        # $GF :05^3A is the precomputed frame for an unknown command with seq=0x05
        # XOR("$GF :05") = 0x24^0x47^0x46^0x20^0x3A^0x30^0x35 = 0x3A
        resp = self._dispatch_raw("$GF :05^3A\r")
        self.assertIn(":05", resp)
        self.assertTrue(resp.startswith("$NK"))


# ---------------------------------------------------------------------------
# Loopback / virtual serial integration tests
# ---------------------------------------------------------------------------

class _SimulatorLoopback:
    """In-memory loopback that simulates the EVSE firmware on the serial bus.

    Bytes written via ``write()`` are parsed as RAPI command frames; the
    dispatcher response for each complete frame is queued and returned by
    subsequent ``read()`` calls.  This lets ``UartTransport`` be tested
    end-to-end without real serial hardware.
    """

    def __init__(self, dispatcher: RapiDispatcher) -> None:
        self._dispatcher = dispatcher
        self._read_buf = bytearray()
        self._stream_parser = RapiStreamParser()
        self.is_open = True

    # serial.Serial-compatible interface consumed by UartTransport
    def write(self, data: bytes) -> None:
        frames = self._stream_parser.feed(data.decode("latin-1"))
        for frame in frames:
            resp = self._dispatcher.dispatch(frame)
            self._read_buf.extend(resp.encode("latin-1"))

    @property
    def in_waiting(self) -> int:
        return len(self._read_buf)

    def read(self, n: int) -> bytes:
        chunk = bytes(self._read_buf[:n])
        self._read_buf = self._read_buf[n:]
        return chunk

    def close(self) -> None:
        self.is_open = False


class TestLoopbackIntegration(unittest.TestCase):
    """End-to-end integration tests over a virtual loopback serial port.

    UartTransport.send_frame() writes the command; the _SimulatorLoopback
    parses it, dispatches it, and queues the response; UartTransport.recv_frames()
    reads and parses the response.  No real serial hardware is required.
    """

    def _make_transport(
        self, model: EvseModel | None = None
    ) -> tuple[UartTransport, _SimulatorLoopback]:
        dispatcher = RapiDispatcher(model if model is not None else EvseModel())
        loopback = _SimulatorLoopback(dispatcher)
        transport = UartTransport("/dev/null")
        transport._conn = loopback  # type: ignore[assignment]
        return transport, loopback

    def test_gv_roundtrip(self) -> None:
        t, _ = self._make_transport()
        t.send_frame("$GV^35\r")
        frames = t.recv_frames()
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].token, "OK")
        # Payload fields should contain FW + RAPI version
        payload = " ".join(frames[0].args)
        self.assertIn("8.2.3", payload)
        self.assertIn("5.2.1-LGT", payload)

    def test_gs_roundtrip_default_model(self) -> None:
        t, _ = self._make_transport()
        t.send_frame("$GS^30\r")
        frames = t.recv_frames()
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].token, "OK")
        # first arg is evse_state hex; default model state A = "01"
        self.assertEqual(frames[0].args[0], "01")

    def test_fd_then_fe_roundtrip(self) -> None:
        model = EvseModel(evse_state=EVSE_STATE_A, enabled=True)
        t, _ = self._make_transport(model)

        # Disable
        t.send_frame("$FD^26\r")
        frames = t.recv_frames()
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].token, "OK")
        self.assertEqual(model.evse_state, EVSE_STATE_DISABLED)

        # Enable
        t.send_frame("$FE^27\r")
        frames = t.recv_frames()
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].token, "OK")
        self.assertEqual(model.evse_state, EVSE_STATE_A)

    def test_sc_roundtrip_clamps_and_echoes(self) -> None:
        model = EvseModel(max_hw_current_capacity=32)
        t, _ = self._make_transport(model)
        t.send_frame("$SC 20\r")
        frames = t.recv_frames()
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].token, "OK")
        self.assertEqual(frames[0].args[0], "20")
        self.assertEqual(model.current_capacity_amps, 20)

    def test_unknown_command_returns_nk_over_loopback(self) -> None:
        t, _ = self._make_transport()
        t.send_frame("$GF\r")
        frames = t.recv_frames()
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].token, "NK")

    def test_bad_checksum_frame_not_dispatched(self) -> None:
        """A command with a wrong checksum must produce no response."""
        t, _ = self._make_transport()
        t.send_frame("$GV^00\r")  # wrong checksum – parser drops it
        frames = t.recv_frames()
        self.assertEqual(len(frames), 0)

    def test_multiple_commands_in_one_write(self) -> None:
        """Multiple frames concatenated in one write must all be dispatched."""
        t, _ = self._make_transport()
        # $GV^35\r + $FD^26\r in one send
        t.send_frame("$GV^35\r$FD^26\r")
        frames = t.recv_frames()
        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0].token, "OK")
        self.assertEqual(frames[1].token, "OK")

    def test_sequence_id_echoed_over_loopback(self) -> None:
        t, _ = self._make_transport()
        t.send_frame("$GV :7A^59\r")
        frames = t.recv_frames()
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].sequence_id, 0x7A)

    def test_g0_connected_via_vflag_over_loopback(self) -> None:
        model = EvseModel(pilot_state=0, vflags=ECVF_EV_CONNECTED)
        t, _ = self._make_transport(model)
        t.send_frame("$G0\r")
        frames = t.recv_frames()
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].args[0], "1")

    def test_partial_frame_buffered_across_writes(self) -> None:
        """RapiStreamParser must buffer a partial frame across multiple writes."""
        t, _ = self._make_transport()
        # Send first half
        t.send_frame("$GV")
        self.assertEqual(t.recv_frames(), [])
        # Send second half including EOC
        t.send_frame("^35\r")
        frames = t.recv_frames()
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].token, "OK")


if __name__ == "__main__":
    unittest.main()
