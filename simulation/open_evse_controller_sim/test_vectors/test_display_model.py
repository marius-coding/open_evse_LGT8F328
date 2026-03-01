"""Tests for Step 9 – DisplayModel state-driven text and colour mapping.

Verifies that DisplayModel.update_from_evse_state() produces the correct
line1/line2 text and backlight colour integer for all EVSE states handled
in OnboardDisplay::Update() (firmware/open_evse/main.cpp:529-773).

Colour constants and string values are cross-checked against:
  - firmware/open_evse/open_evse.h:640-646      (colour #defines)
  - firmware/open_evse/Language_default.h       (string macros)
  - firmware/open_evse/strings.cpp              (PROGMEM assignments)
"""

import unittest

from open_evse_controller_sim.display_model import (
    LCD_GREEN,
    LCD_RED,
    LCD_TEAL,
    LCD_VIOLET,
    LCD_WHITE,
    LCD_YELLOW,
    STR_CHARGING,
    STR_CONNECTED,
    STR_DIODE_CHECK_FAILED,
    STR_DISABLED,
    STR_EVSE_ERROR,
    STR_GFCI_FAULT,
    STR_NO_GROUND,
    STR_READY,
    STR_SLEEPING,
    STR_STUCK_RELAY,
    STR_VENT_REQUIRED,
    DisplayModel,
)
from open_evse_controller_sim.evse_model import (
    ECVF_EV_CONNECTED,
    EVSE_STATE_A,
    EVSE_STATE_B,
    EVSE_STATE_C,
    EVSE_STATE_D,
    EVSE_STATE_DIODE_CHK_FAILED,
    EVSE_STATE_DISABLED,
    EVSE_STATE_GFCI_FAULT,
    EVSE_STATE_NO_GROUND,
    EVSE_STATE_SLEEPING,
    EVSE_STATE_STUCK_RELAY,
    EvseModel,
)


def _make_display(state: int, vflags: int = 0) -> DisplayModel:
    model = EvseModel(evse_state=state, vflags=vflags)
    d = DisplayModel()
    d.update_from_evse_state(model)
    return d


class TestDisplayColourConstants(unittest.TestCase):
    """Colour integer values must match firmware open_evse.h:640-646."""

    def test_red_value(self) -> None:
        self.assertEqual(LCD_RED, 0x1)

    def test_green_value(self) -> None:
        self.assertEqual(LCD_GREEN, 0x2)

    def test_yellow_value(self) -> None:
        self.assertEqual(LCD_YELLOW, 0x3)

    def test_violet_value(self) -> None:
        self.assertEqual(LCD_VIOLET, 0x5)

    def test_teal_value(self) -> None:
        self.assertEqual(LCD_TEAL, 0x6)

    def test_white_value(self) -> None:
        self.assertEqual(LCD_WHITE, 0x7)


class TestDisplayStringConstants(unittest.TestCase):
    """String values must match Language_default.h macros."""

    def test_ready(self) -> None:
        self.assertEqual(STR_READY, "Ready")

    def test_connected(self) -> None:
        self.assertEqual(STR_CONNECTED, "Connected")

    def test_charging(self) -> None:
        self.assertEqual(STR_CHARGING, "Charging")

    def test_disabled(self) -> None:
        self.assertEqual(STR_DISABLED, "Disabled")

    def test_sleeping(self) -> None:
        self.assertEqual(STR_SLEEPING, "Sleeping")

    def test_evse_error(self) -> None:
        self.assertEqual(STR_EVSE_ERROR, "EVSE ERROR")

    def test_vent_required(self) -> None:
        self.assertEqual(STR_VENT_REQUIRED, "VENT REQUIRED")

    def test_diode_check_failed(self) -> None:
        self.assertEqual(STR_DIODE_CHECK_FAILED, "DIODE CHECK")

    def test_gfci_fault(self) -> None:
        self.assertEqual(STR_GFCI_FAULT, "GFCI FAULT")

    def test_no_ground(self) -> None:
        self.assertEqual(STR_NO_GROUND, "NO GROUND")

    def test_stuck_relay(self) -> None:
        self.assertEqual(STR_STUCK_RELAY, "STUCK RELAY")


class TestDisplayDefaultState(unittest.TestCase):
    """Default DisplayModel should show State-A (Ready/GREEN) values."""

    def test_default_line1(self) -> None:
        self.assertEqual(DisplayModel().line1, STR_READY)

    def test_default_line2(self) -> None:
        self.assertEqual(DisplayModel().line2, "")

    def test_default_color(self) -> None:
        self.assertEqual(DisplayModel().color, LCD_GREEN)


class TestStateA(unittest.TestCase):
    def setUp(self) -> None:
        self.d = _make_display(EVSE_STATE_A)

    def test_color_is_green(self) -> None:
        self.assertEqual(self.d.color, LCD_GREEN)

    def test_line1_is_ready(self) -> None:
        self.assertEqual(self.d.line1, STR_READY)

    def test_line2_is_empty(self) -> None:
        self.assertEqual(self.d.line2, "")


class TestStateB(unittest.TestCase):
    def setUp(self) -> None:
        self.d = _make_display(EVSE_STATE_B)

    def test_color_is_yellow(self) -> None:
        self.assertEqual(self.d.color, LCD_YELLOW)

    def test_line1_is_connected(self) -> None:
        self.assertEqual(self.d.line1, STR_CONNECTED)

    def test_line2_is_empty(self) -> None:
        self.assertEqual(self.d.line2, "")


class TestStateC(unittest.TestCase):
    def setUp(self) -> None:
        self.d = _make_display(EVSE_STATE_C)

    def test_color_is_teal(self) -> None:
        self.assertEqual(self.d.color, LCD_TEAL)

    def test_line1_is_charging(self) -> None:
        self.assertEqual(self.d.line1, STR_CHARGING)

    def test_line2_is_empty(self) -> None:
        self.assertEqual(self.d.line2, "")


class TestStateD(unittest.TestCase):
    def setUp(self) -> None:
        self.d = _make_display(EVSE_STATE_D)

    def test_color_is_red(self) -> None:
        self.assertEqual(self.d.color, LCD_RED)

    def test_line1_is_evse_error(self) -> None:
        self.assertEqual(self.d.line1, STR_EVSE_ERROR)

    def test_line2_is_vent_required(self) -> None:
        self.assertEqual(self.d.line2, STR_VENT_REQUIRED)


class TestStateDiodeChkFailed(unittest.TestCase):
    def setUp(self) -> None:
        self.d = _make_display(EVSE_STATE_DIODE_CHK_FAILED)

    def test_color_is_red(self) -> None:
        self.assertEqual(self.d.color, LCD_RED)

    def test_line1_is_evse_error(self) -> None:
        self.assertEqual(self.d.line1, STR_EVSE_ERROR)

    def test_line2_is_diode_check(self) -> None:
        self.assertEqual(self.d.line2, STR_DIODE_CHECK_FAILED)


class TestStateGfciFault(unittest.TestCase):
    def setUp(self) -> None:
        self.d = _make_display(EVSE_STATE_GFCI_FAULT)

    def test_color_is_red(self) -> None:
        self.assertEqual(self.d.color, LCD_RED)

    def test_line1_is_gfci_fault(self) -> None:
        self.assertEqual(self.d.line1, STR_GFCI_FAULT)

    def test_line2_is_empty(self) -> None:
        self.assertEqual(self.d.line2, "")


class TestStateNoGround(unittest.TestCase):
    def setUp(self) -> None:
        self.d = _make_display(EVSE_STATE_NO_GROUND)

    def test_color_is_red(self) -> None:
        self.assertEqual(self.d.color, LCD_RED)

    def test_line1_is_no_ground(self) -> None:
        self.assertEqual(self.d.line1, STR_NO_GROUND)

    def test_line2_is_empty(self) -> None:
        self.assertEqual(self.d.line2, "")


class TestStateStuckRelay(unittest.TestCase):
    def setUp(self) -> None:
        self.d = _make_display(EVSE_STATE_STUCK_RELAY)

    def test_color_is_red(self) -> None:
        self.assertEqual(self.d.color, LCD_RED)

    def test_line1_is_evse_error(self) -> None:
        self.assertEqual(self.d.line1, STR_EVSE_ERROR)

    def test_line2_is_stuck_relay(self) -> None:
        self.assertEqual(self.d.line2, STR_STUCK_RELAY)


class TestStateDisabled(unittest.TestCase):
    def setUp(self) -> None:
        self.d = _make_display(EVSE_STATE_DISABLED)

    def test_color_is_violet(self) -> None:
        self.assertEqual(self.d.color, LCD_VIOLET)

    def test_line1_is_disabled(self) -> None:
        self.assertEqual(self.d.line1, STR_DISABLED)

    def test_line2_is_empty(self) -> None:
        self.assertEqual(self.d.line2, "")


class TestStateSleepingDisconnected(unittest.TestCase):
    """SLEEPING + EV not connected → VIOLET."""

    def setUp(self) -> None:
        self.d = _make_display(EVSE_STATE_SLEEPING, vflags=0x0000)

    def test_color_is_violet(self) -> None:
        self.assertEqual(self.d.color, LCD_VIOLET)

    def test_line1_is_sleeping(self) -> None:
        self.assertEqual(self.d.line1, STR_SLEEPING)

    def test_line2_is_empty(self) -> None:
        self.assertEqual(self.d.line2, "")


class TestStateSleepingConnected(unittest.TestCase):
    """SLEEPING + ECVF_EV_CONNECTED set results in WHITE backlight (main.cpp:757)."""

    def setUp(self) -> None:
        self.d = _make_display(EVSE_STATE_SLEEPING, vflags=ECVF_EV_CONNECTED)

    def test_color_is_white(self) -> None:
        self.assertEqual(self.d.color, LCD_WHITE)

    def test_line1_is_sleeping(self) -> None:
        self.assertEqual(self.d.line1, STR_SLEEPING)


class TestUnknownStateFallback(unittest.TestCase):
    """Any unrecognised state integer should fall back to RED / EVSE ERROR."""

    def _display(self, state: int) -> DisplayModel:
        return _make_display(state)

    def test_color_is_red(self) -> None:
        self.assertEqual(self._display(0x09).color, LCD_RED)

    def test_line1_is_evse_error(self) -> None:
        self.assertEqual(self._display(0x09).line1, STR_EVSE_ERROR)

    def test_line2_is_empty(self) -> None:
        self.assertEqual(self._display(0x09).line2, "")


class TestDisplayUpdatesInPlace(unittest.TestCase):
    """update_from_evse_state() must update the existing object, not replace it."""

    def test_mutates_same_object(self) -> None:
        d = DisplayModel()
        model_c = EvseModel(evse_state=EVSE_STATE_C)
        d.update_from_evse_state(model_c)
        self.assertEqual(d.color, LCD_TEAL)
        self.assertEqual(d.line1, STR_CHARGING)
        # Mutate again
        model_a = EvseModel(evse_state=EVSE_STATE_A)
        d.update_from_evse_state(model_a)
        self.assertEqual(d.color, LCD_GREEN)
        self.assertEqual(d.line1, STR_READY)


class TestDisplayIntegrationWithStateEngine(unittest.TestCase):
    """DisplayModel stays coherent when driven by EvseStateEngine transitions."""

    def test_inject_fault_shows_gfci_display(self) -> None:
        from open_evse_controller_sim.evse_model import EvseStateEngine

        engine = EvseStateEngine()
        d = DisplayModel()
        engine.inject_gfi_fault()
        d.update_from_evse_state(engine.model)
        self.assertEqual(d.color, LCD_RED)
        self.assertEqual(d.line1, STR_GFCI_FAULT)

    def test_disable_shows_disabled_display(self) -> None:
        from open_evse_controller_sim.evse_model import EvseStateEngine

        engine = EvseStateEngine()
        d = DisplayModel()
        engine.disable()
        d.update_from_evse_state(engine.model)
        self.assertEqual(d.color, LCD_VIOLET)
        self.assertEqual(d.line1, STR_DISABLED)

    def test_charging_shows_teal(self) -> None:
        from open_evse_controller_sim.evse_model import EvseStateEngine, VehicleResponse

        engine = EvseStateEngine()
        d = DisplayModel()
        engine.set_vehicle_response(VehicleResponse.CHARGING)
        d.update_from_evse_state(engine.model)
        self.assertEqual(d.color, LCD_TEAL)
        self.assertEqual(d.line1, STR_CHARGING)


if __name__ == "__main__":
    unittest.main()
