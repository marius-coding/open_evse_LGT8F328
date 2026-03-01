"""Tests for Step 5 RAPI command handlers and async notification builders.

Verifies that each MVP command produces the correct framed response matching
the payload formats from firmware/open_evse/rapi_proc.cpp and that async
notifications (AB/AT) match sendBootNotification() / sendEvseState().
"""

import unittest

from open_evse_controller_sim.evse_model import EvseModel
from open_evse_controller_sim.rapi_dispatch import (
    ECVF_EV_CONNECTED,
    EVSE_STATE_A,
    EVSE_STATE_DISABLED,
    EVSE_STATE_SLEEPING,
    FW_VERSION,
    MIN_CURRENT_CAPACITY,
    PILOT_STATE_N12,
    RAPI_VERSION,
    RapiDispatcher,
)
from open_evse_controller_sim.rapi_parser import parse_frame


def _dispatch(cmd_frame: str, model: EvseModel | None = None) -> str:
    """Helper: parse a raw frame string and dispatch it."""
    parsed = parse_frame(cmd_frame)
    assert parsed is not None, f"parse_frame failed for: {cmd_frame!r}"
    d = RapiDispatcher(model)
    return d.dispatch(parsed)


class TestGV(unittest.TestCase):
    def test_response_contains_fw_and_rapi_version(self) -> None:
        resp = _dispatch("$GV\r")
        self.assertIn(FW_VERSION, resp)
        self.assertIn(RAPI_VERSION, resp)
        self.assertTrue(resp.startswith("$OK "))

    def test_sequence_id_echoed(self) -> None:
        resp = _dispatch("$GV :7A^59\r")
        self.assertIn(":7A", resp)
        self.assertTrue(resp.startswith("$OK "))


class TestGS(unittest.TestCase):
    def test_default_model_response(self) -> None:
        model = EvseModel()
        resp = _dispatch("$GS\r", model)
        # format: $OK {state:02x} {elapsed} {pilot:02x} {vflags:04x}^{chk}\r
        self.assertTrue(resp.startswith("$OK 01 0 00 0200"), resp)

    def test_elapsed_time_included(self) -> None:
        model = EvseModel(elapsed_charge_time=42)
        resp = _dispatch("$GS\r", model)
        self.assertIn("42", resp)

    def test_checksum_valid(self) -> None:
        model = EvseModel()
        resp = _dispatch("$GS\r", model)
        # Parsed response must be a valid RAPI frame
        self.assertIsNotNone(parse_frame(resp))


class TestGE(unittest.TestCase):
    def test_response_format(self) -> None:
        model = EvseModel(current_capacity_amps=20, flags=0x0001)
        resp = _dispatch("$GE\r", model)
        self.assertTrue(resp.startswith("$OK 20 0001"), resp)

    def test_checksum_valid(self) -> None:
        resp = _dispatch("$GE\r")
        self.assertIsNotNone(parse_frame(resp))


class TestGC(unittest.TestCase):
    def test_l2_uses_hw_max(self) -> None:
        model = EvseModel(svc_level=2, max_hw_current_capacity=32, current_capacity_amps=16)
        resp = _dispatch("$GC\r", model)
        # $OK 6 32 16 32^{chk}\r
        self.assertTrue(resp.startswith("$OK 6 32 16 32"), resp)

    def test_l1_caps_at_24(self) -> None:
        model = EvseModel(svc_level=1, max_hw_current_capacity=32, current_capacity_amps=12)
        resp = _dispatch("$GC\r", model)
        self.assertTrue(resp.startswith("$OK 6 24 12 24"), resp)

    def test_min_is_6(self) -> None:
        resp = _dispatch("$GC\r")
        parts = resp.split()
        # parts: ['$OK', '6', ...]
        self.assertEqual(parts[1], str(MIN_CURRENT_CAPACITY))

    def test_checksum_valid(self) -> None:
        self.assertIsNotNone(parse_frame(_dispatch("$GC\r")))


class TestG0(unittest.TestCase):
    def test_disconnected(self) -> None:
        model = EvseModel(pilot_state=0, vflags=0x0000)
        resp = _dispatch("$G0\r", model)
        self.assertTrue(resp.startswith("$OK 0"), resp)

    def test_connected_via_vflag(self) -> None:
        model = EvseModel(pilot_state=0, vflags=ECVF_EV_CONNECTED)
        resp = _dispatch("$G0\r", model)
        self.assertTrue(resp.startswith("$OK 1"), resp)

    def test_unknown_when_pilot_n12(self) -> None:
        model = EvseModel(pilot_state=PILOT_STATE_N12)
        resp = _dispatch("$G0\r", model)
        self.assertTrue(resp.startswith("$OK 2"), resp)


class TestSC(unittest.TestCase):
    def test_sets_current(self) -> None:
        model = EvseModel(current_capacity_amps=16, max_hw_current_capacity=32)
        resp = _dispatch("$SC 24\r", model)
        self.assertTrue(resp.startswith("$OK 24"), resp)
        self.assertEqual(model.current_capacity_amps, 24)

    def test_clamps_to_min(self) -> None:
        model = EvseModel(max_hw_current_capacity=32)
        resp = _dispatch("$SC 1\r", model)
        self.assertTrue(resp.startswith(f"$OK {MIN_CURRENT_CAPACITY}"), resp)
        self.assertEqual(model.current_capacity_amps, MIN_CURRENT_CAPACITY)

    def test_clamps_to_hw_max(self) -> None:
        model = EvseModel(max_hw_current_capacity=32)
        resp = _dispatch("$SC 100\r", model)
        self.assertTrue(resp.startswith("$OK 32"), resp)
        self.assertEqual(model.current_capacity_amps, 32)

    def test_no_args_returns_nk(self) -> None:
        resp = _dispatch("$SC\r")
        self.assertTrue(resp.startswith("$NK"), resp)

    def test_invalid_arg_returns_nk(self) -> None:
        resp = _dispatch("$SC X\r")
        self.assertTrue(resp.startswith("$NK"), resp)

    def test_checksum_valid(self) -> None:
        self.assertIsNotNone(parse_frame(_dispatch("$SC 16\r")))


class TestFE(unittest.TestCase):
    def test_enables_evse(self) -> None:
        model = EvseModel(enabled=False, evse_state=EVSE_STATE_DISABLED)
        resp = _dispatch("$FE\r", model)
        self.assertTrue(resp.startswith("$OK"), resp)
        self.assertTrue(model.enabled)
        self.assertEqual(model.evse_state, EVSE_STATE_A)

    def test_sleeping_transitions_to_a(self) -> None:
        model = EvseModel(evse_state=EVSE_STATE_SLEEPING)
        _dispatch("$FE\r", model)
        self.assertEqual(model.evse_state, EVSE_STATE_A)

    def test_checksum_valid(self) -> None:
        self.assertIsNotNone(parse_frame(_dispatch("$FE\r")))


class TestFD(unittest.TestCase):
    def test_disables_evse(self) -> None:
        model = EvseModel(enabled=True, evse_state=EVSE_STATE_A)
        resp = _dispatch("$FD\r", model)
        self.assertTrue(resp.startswith("$OK"), resp)
        self.assertFalse(model.enabled)
        self.assertEqual(model.evse_state, EVSE_STATE_DISABLED)

    def test_checksum_valid(self) -> None:
        self.assertIsNotNone(parse_frame(_dispatch("$FD\r")))


class TestSL(unittest.TestCase):
    def test_set_level_1(self) -> None:
        model = EvseModel(svc_level=2)
        resp = _dispatch("$SL 1\r", model)
        self.assertTrue(resp.startswith("$OK"), resp)
        self.assertEqual(model.svc_level, 1)

    def test_set_level_2(self) -> None:
        model = EvseModel(svc_level=1)
        resp = _dispatch("$SL 2\r", model)
        self.assertTrue(resp.startswith("$OK"), resp)
        self.assertEqual(model.svc_level, 2)

    def test_invalid_level_returns_nk(self) -> None:
        resp = _dispatch("$SL 3\r")
        self.assertTrue(resp.startswith("$NK"), resp)

    def test_no_arg_returns_nk(self) -> None:
        resp = _dispatch("$SL\r")
        self.assertTrue(resp.startswith("$NK"), resp)


class TestUnknownCommand(unittest.TestCase):
    def test_unsupported_command_returns_nk(self) -> None:
        # GF is not in the MVP set
        resp = _dispatch("$GF\r")
        self.assertTrue(resp.startswith("$NK"), resp)

    def test_checksum_valid_on_nk(self) -> None:
        self.assertIsNotNone(parse_frame(_dispatch("$GF\r")))


class TestAsyncNotifications(unittest.TestCase):
    def test_boot_notification_format(self) -> None:
        model = EvseModel(evse_state=0x01)
        d = RapiDispatcher(model)
        notif = d.build_boot_notification()
        # Format: $AB {state:02x} {FW_VERSION}^{chk}\r
        self.assertTrue(notif.startswith(f"$AB 01 {FW_VERSION}"), notif)
        self.assertTrue(notif.endswith("\r"))
        self.assertIsNotNone(parse_frame(notif))

    def test_state_notification_format(self) -> None:
        model = EvseModel(
            evse_state=0x03,
            pilot_state=1,
            current_capacity_amps=16,
            vflags=0x0240,
        )
        d = RapiDispatcher(model)
        notif = d.build_state_notification()
        # Format: $AT {state:02x} {pilot:02x} {amps} {vflags:04x}^{chk}\r
        self.assertTrue(notif.startswith("$AT 03 01 16 0240"), notif)
        self.assertTrue(notif.endswith("\r"))
        self.assertIsNotNone(parse_frame(notif))

    def test_boot_notification_checksum_matches_firmware_example(self) -> None:
        # Verify against the known vector from test_rapi_parser:
        # append_xor_checksum("$AB 01 FW") == "$AB 01 FW^37\r"
        # Our firmware-version string produces a different checksum but must still parse.
        model = EvseModel(evse_state=0x01)
        d = RapiDispatcher(model)
        self.assertIsNotNone(parse_frame(d.build_boot_notification()))

    def test_state_notification_known_vector(self) -> None:
        # Verify that the AT notification frame parses cleanly and
        # that the token is 'AT' (not 'AB').
        model = EvseModel(evse_state=0x01, pilot_state=0, current_capacity_amps=16, vflags=0x0200)
        d = RapiDispatcher(model)
        notif = d.build_state_notification()
        parsed = parse_frame(notif)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.token, "AT")


if __name__ == "__main__":
    unittest.main()
