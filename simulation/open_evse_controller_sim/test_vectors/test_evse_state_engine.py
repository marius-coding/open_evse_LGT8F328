"""Tests for Steps 6, 7, 8 – EVSE state engine, operator controls, fault injection.

Verifies that EvseStateEngine transitions the EvseModel correctly so that
GS/GE/GC responses (read directly from EvseModel) remain coherent after
operator and fault-injection events.

Firmware references:
  J1772EvseController.cpp:1253-1601  – state transitions / debounce
  J1772EvseController.cpp:1348-1510  – fault entry paths
  open_evse.h:587-590                – debounce timing constants
"""

import unittest

from open_evse_controller_sim.evse_model import (
    DELAY_STATE_TRANSITION_A_MS,
    DELAY_STATE_TRANSITION_MS,
    ECVF_CHARGING_ON,
    ECVF_GFI_TRIPPED,
    ECVF_HARD_FAULT,
    ECVF_NOGND_TRIPPED,
    EVSE_STATE_A,
    EVSE_STATE_B,
    EVSE_STATE_C,
    EVSE_STATE_DIODE_CHK_FAILED,
    EVSE_STATE_DISABLED,
    EVSE_STATE_GFCI_FAULT,
    EVSE_STATE_NO_GROUND,
    EVSE_STATE_SLEEPING,
    EVSE_STATE_STUCK_RELAY,
    MAX_CURRENT_CAPACITY_L1,
    MIN_CURRENT_CAPACITY_J1772,
    PILOT_STATE_P12,
    PILOT_STATE_PWM,
    EvseModel,
    EvseStateEngine,
    VehicleResponse,
)


class TestDebounceConstants(unittest.TestCase):
    """Step 6 – timing constants match firmware open_evse.h values."""

    def test_state_transition_delay(self) -> None:
        self.assertEqual(EvseStateEngine.DELAY_STATE_TRANSITION_MS, 250)

    def test_state_transition_a_delay(self) -> None:
        self.assertEqual(EvseStateEngine.DELAY_STATE_TRANSITION_A_MS, 25)

    def test_module_level_constants(self) -> None:
        self.assertEqual(DELAY_STATE_TRANSITION_MS, 250)
        self.assertEqual(DELAY_STATE_TRANSITION_A_MS, 25)


class TestEvseStateEngineInit(unittest.TestCase):
    """Step 6 – EvseStateEngine initialises with a default or provided model."""

    def test_default_model_created(self) -> None:
        engine = EvseStateEngine()
        self.assertIsInstance(engine.model, EvseModel)
        self.assertEqual(engine.model.evse_state, EVSE_STATE_A)

    def test_shared_model_is_same_object(self) -> None:
        model = EvseModel()
        engine = EvseStateEngine(model)
        self.assertIs(engine.model, model)

    def test_fault_model_initialised(self) -> None:
        engine = EvseStateEngine()
        self.assertFalse(engine.fault.gfi_trip)
        self.assertFalse(engine.fault.no_ground)
        self.assertFalse(engine.fault.stuck_relay)
        self.assertFalse(engine.fault.diode_fault)


# ---------------------------------------------------------------------------
# Step 7 – operator controls: vehicle response
# ---------------------------------------------------------------------------

class TestVehicleResponseDisconnected(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = EvseStateEngine(EvseModel(evse_state=EVSE_STATE_B))

    def test_state_set_to_a(self) -> None:
        self.engine.set_vehicle_response(VehicleResponse.DISCONNECTED)
        self.assertEqual(self.engine.model.evse_state, EVSE_STATE_A)

    def test_pilot_set_to_p12(self) -> None:
        self.engine.set_vehicle_response(VehicleResponse.DISCONNECTED)
        self.assertEqual(self.engine.model.pilot_state, PILOT_STATE_P12)

    def test_ev_connected_flag_cleared(self) -> None:
        self.engine.model.vflags |= ECVF_CHARGING_ON
        self.engine.set_vehicle_response(VehicleResponse.DISCONNECTED)
        self.assertFalse(self.engine.model.vflags & ECVF_CHARGING_ON)


class TestVehicleResponseConnectedIdle(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = EvseStateEngine()

    def test_state_set_to_b(self) -> None:
        self.engine.set_vehicle_response(VehicleResponse.CONNECTED_IDLE)
        self.assertEqual(self.engine.model.evse_state, EVSE_STATE_B)

    def test_pilot_set_to_pwm(self) -> None:
        self.engine.set_vehicle_response(VehicleResponse.CONNECTED_IDLE)
        self.assertEqual(self.engine.model.pilot_state, PILOT_STATE_PWM)

    def test_charging_on_cleared(self) -> None:
        self.engine.model.vflags |= ECVF_CHARGING_ON
        self.engine.set_vehicle_response(VehicleResponse.CONNECTED_IDLE)
        self.assertFalse(self.engine.model.vflags & ECVF_CHARGING_ON)


class TestVehicleResponseCharging(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = EvseStateEngine()

    def test_state_set_to_c(self) -> None:
        self.engine.set_vehicle_response(VehicleResponse.CHARGING)
        self.assertEqual(self.engine.model.evse_state, EVSE_STATE_C)

    def test_pilot_set_to_pwm(self) -> None:
        self.engine.set_vehicle_response(VehicleResponse.CHARGING)
        self.assertEqual(self.engine.model.pilot_state, PILOT_STATE_PWM)

    def test_charging_on_flag_set(self) -> None:
        self.engine.set_vehicle_response(VehicleResponse.CHARGING)
        self.assertTrue(self.engine.model.vflags & ECVF_CHARGING_ON)


class TestVehicleResponseBlockedWhenDisabled(unittest.TestCase):
    def test_disabled_blocks_vehicle_response(self) -> None:
        engine = EvseStateEngine(EvseModel(evse_state=EVSE_STATE_DISABLED))
        engine.set_vehicle_response(VehicleResponse.CHARGING)
        self.assertEqual(engine.model.evse_state, EVSE_STATE_DISABLED)

    def test_sleeping_blocks_vehicle_response(self) -> None:
        engine = EvseStateEngine(EvseModel(evse_state=EVSE_STATE_SLEEPING))
        engine.set_vehicle_response(VehicleResponse.CHARGING)
        self.assertEqual(engine.model.evse_state, EVSE_STATE_SLEEPING)


class TestVehicleResponseBlockedDuringFault(unittest.TestCase):
    def test_fault_state_blocks_vehicle_response(self) -> None:
        engine = EvseStateEngine(EvseModel(evse_state=EVSE_STATE_GFCI_FAULT))
        engine.set_vehicle_response(VehicleResponse.CHARGING)
        self.assertEqual(engine.model.evse_state, EVSE_STATE_GFCI_FAULT)


# ---------------------------------------------------------------------------
# Step 7 – operator controls: enable / disable / sleep / current capacity
# ---------------------------------------------------------------------------

class TestEnable(unittest.TestCase):
    def test_enable_from_disabled(self) -> None:
        engine = EvseStateEngine(EvseModel(enabled=False, evse_state=EVSE_STATE_DISABLED))
        engine.enable()
        self.assertTrue(engine.model.enabled)
        self.assertEqual(engine.model.evse_state, EVSE_STATE_A)

    def test_enable_from_sleeping(self) -> None:
        engine = EvseStateEngine(EvseModel(evse_state=EVSE_STATE_SLEEPING))
        engine.enable()
        self.assertEqual(engine.model.evse_state, EVSE_STATE_A)
        self.assertEqual(engine.model.pilot_state, PILOT_STATE_P12)

    def test_enable_already_enabled_stays_in_a(self) -> None:
        engine = EvseStateEngine(EvseModel(evse_state=EVSE_STATE_A, enabled=True))
        engine.enable()
        self.assertEqual(engine.model.evse_state, EVSE_STATE_A)


class TestDisable(unittest.TestCase):
    def test_disable_from_charging(self) -> None:
        engine = EvseStateEngine(EvseModel(
            evse_state=EVSE_STATE_C,
            enabled=True,
            vflags=ECVF_CHARGING_ON,
        ))
        engine.disable()
        self.assertFalse(engine.model.enabled)
        self.assertEqual(engine.model.evse_state, EVSE_STATE_DISABLED)
        self.assertFalse(engine.model.vflags & ECVF_CHARGING_ON)

    def test_disable_from_a(self) -> None:
        engine = EvseStateEngine()
        engine.disable()
        self.assertEqual(engine.model.evse_state, EVSE_STATE_DISABLED)
        self.assertFalse(engine.model.enabled)


class TestSleep(unittest.TestCase):
    def test_sleep_from_charging(self) -> None:
        engine = EvseStateEngine(EvseModel(
            evse_state=EVSE_STATE_C,
            vflags=ECVF_CHARGING_ON,
        ))
        engine.sleep()
        self.assertEqual(engine.model.evse_state, EVSE_STATE_SLEEPING)
        self.assertFalse(engine.model.vflags & ECVF_CHARGING_ON)

    def test_sleep_from_b(self) -> None:
        engine = EvseStateEngine(EvseModel(evse_state=EVSE_STATE_B))
        engine.sleep()
        self.assertEqual(engine.model.evse_state, EVSE_STATE_SLEEPING)


class TestSetCurrentCapacity(unittest.TestCase):
    def test_sets_within_range_l2(self) -> None:
        engine = EvseStateEngine(EvseModel(svc_level=2, max_hw_current_capacity=32))
        engine.set_current_capacity(24)
        self.assertEqual(engine.model.current_capacity_amps, 24)

    def test_clamps_to_min(self) -> None:
        engine = EvseStateEngine(EvseModel(svc_level=2, max_hw_current_capacity=32))
        engine.set_current_capacity(1)
        self.assertEqual(engine.model.current_capacity_amps, MIN_CURRENT_CAPACITY_J1772)

    def test_clamps_to_hw_max_l2(self) -> None:
        engine = EvseStateEngine(EvseModel(svc_level=2, max_hw_current_capacity=32))
        engine.set_current_capacity(100)
        self.assertEqual(engine.model.current_capacity_amps, 32)

    def test_clamps_to_l1_max(self) -> None:
        engine = EvseStateEngine(EvseModel(svc_level=1, max_hw_current_capacity=32))
        engine.set_current_capacity(30)
        self.assertEqual(engine.model.current_capacity_amps, MAX_CURRENT_CAPACITY_L1)

    def test_gs_ge_gc_remain_coherent_after_set(self) -> None:
        """After set_current_capacity, GC min/max/cur fields are coherent."""
        from open_evse_controller_sim.rapi_dispatch import RapiDispatcher
        from open_evse_controller_sim.rapi_parser import parse_frame

        engine = EvseStateEngine(EvseModel(svc_level=2, max_hw_current_capacity=32))
        dispatcher = RapiDispatcher(engine.model)
        engine.set_current_capacity(20)

        gc_resp = dispatcher.dispatch(parse_frame("$GC\r"))
        self.assertIn("20", gc_resp)
        ge_resp = dispatcher.dispatch(parse_frame("$GE\r"))
        self.assertIn("20", ge_resp)


# ---------------------------------------------------------------------------
# Step 8 – fault injection
# ---------------------------------------------------------------------------

class TestInjectGfiFault(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = EvseStateEngine(EvseModel(
            evse_state=EVSE_STATE_C, vflags=ECVF_CHARGING_ON,
        ))
        self.engine.inject_gfi_fault()

    def test_state_is_gfci_fault(self) -> None:
        self.assertEqual(self.engine.model.evse_state, EVSE_STATE_GFCI_FAULT)

    def test_hard_fault_flag_set(self) -> None:
        self.assertTrue(self.engine.model.vflags & ECVF_HARD_FAULT)

    def test_gfi_tripped_flag_set(self) -> None:
        self.assertTrue(self.engine.model.vflags & ECVF_GFI_TRIPPED)

    def test_charging_on_cleared(self) -> None:
        self.assertFalse(self.engine.model.vflags & ECVF_CHARGING_ON)

    def test_fault_model_flag_set(self) -> None:
        self.assertTrue(self.engine.fault.gfi_trip)


class TestInjectNoGroundFault(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = EvseStateEngine(EvseModel(
            evse_state=EVSE_STATE_C, vflags=ECVF_CHARGING_ON,
        ))
        self.engine.inject_no_ground_fault()

    def test_state_is_no_ground(self) -> None:
        self.assertEqual(self.engine.model.evse_state, EVSE_STATE_NO_GROUND)

    def test_hard_fault_flag_set(self) -> None:
        self.assertTrue(self.engine.model.vflags & ECVF_HARD_FAULT)

    def test_nognd_tripped_flag_set(self) -> None:
        self.assertTrue(self.engine.model.vflags & ECVF_NOGND_TRIPPED)

    def test_charging_on_cleared(self) -> None:
        self.assertFalse(self.engine.model.vflags & ECVF_CHARGING_ON)

    def test_fault_model_flag_set(self) -> None:
        self.assertTrue(self.engine.fault.no_ground)


class TestInjectStuckRelayFault(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = EvseStateEngine(EvseModel(
            evse_state=EVSE_STATE_C, vflags=ECVF_CHARGING_ON,
        ))
        self.engine.inject_stuck_relay_fault()

    def test_state_is_stuck_relay(self) -> None:
        self.assertEqual(self.engine.model.evse_state, EVSE_STATE_STUCK_RELAY)

    def test_hard_fault_flag_set(self) -> None:
        self.assertTrue(self.engine.model.vflags & ECVF_HARD_FAULT)

    def test_charging_on_cleared(self) -> None:
        self.assertFalse(self.engine.model.vflags & ECVF_CHARGING_ON)

    def test_fault_model_flag_set(self) -> None:
        self.assertTrue(self.engine.fault.stuck_relay)


class TestInjectDiodeFault(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = EvseStateEngine(EvseModel(evse_state=EVSE_STATE_B))
        self.engine.inject_diode_fault()

    def test_state_is_diode_chk_failed(self) -> None:
        self.assertEqual(self.engine.model.evse_state, EVSE_STATE_DIODE_CHK_FAILED)

    def test_hard_fault_flag_set(self) -> None:
        self.assertTrue(self.engine.model.vflags & ECVF_HARD_FAULT)

    def test_fault_model_flag_set(self) -> None:
        self.assertTrue(self.engine.fault.diode_fault)


class TestClearFault(unittest.TestCase):
    def _engine_with_gfi(self) -> EvseStateEngine:
        engine = EvseStateEngine(EvseModel(evse_state=EVSE_STATE_C, vflags=ECVF_CHARGING_ON))
        engine.inject_gfi_fault()
        return engine

    def test_state_returns_to_a(self) -> None:
        engine = self._engine_with_gfi()
        engine.clear_fault()
        self.assertEqual(engine.model.evse_state, EVSE_STATE_A)

    def test_pilot_returns_to_p12(self) -> None:
        engine = self._engine_with_gfi()
        engine.clear_fault()
        self.assertEqual(engine.model.pilot_state, PILOT_STATE_P12)

    def test_hard_fault_cleared(self) -> None:
        engine = self._engine_with_gfi()
        engine.clear_fault()
        self.assertFalse(engine.model.vflags & ECVF_HARD_FAULT)

    def test_charging_on_cleared(self) -> None:
        engine = self._engine_with_gfi()
        engine.clear_fault()
        self.assertFalse(engine.model.vflags & ECVF_CHARGING_ON)

    def test_all_fault_model_flags_cleared(self) -> None:
        engine = EvseStateEngine(EvseModel(evse_state=EVSE_STATE_C, vflags=ECVF_CHARGING_ON))
        engine.inject_gfi_fault()
        engine.inject_no_ground_fault()
        engine.inject_stuck_relay_fault()
        engine.inject_diode_fault()
        engine.clear_fault()
        self.assertFalse(engine.fault.gfi_trip)
        self.assertFalse(engine.fault.no_ground)
        self.assertFalse(engine.fault.stuck_relay)
        self.assertFalse(engine.fault.diode_fault)


class TestFaultStateBlocksVehicleResponse(unittest.TestCase):
    """Step 6/8 integration: fault state prevents operator from changing vehicle."""

    def test_gfi_fault_blocks_vehicle_response(self) -> None:
        engine = EvseStateEngine(EvseModel(evse_state=EVSE_STATE_B))
        engine.inject_gfi_fault()
        engine.set_vehicle_response(VehicleResponse.CHARGING)
        self.assertEqual(engine.model.evse_state, EVSE_STATE_GFCI_FAULT)

    def test_clear_then_vehicle_response_accepted(self) -> None:
        engine = EvseStateEngine(EvseModel(evse_state=EVSE_STATE_B))
        engine.inject_gfi_fault()
        engine.clear_fault()
        engine.set_vehicle_response(VehicleResponse.CONNECTED_IDLE)
        self.assertEqual(engine.model.evse_state, EVSE_STATE_B)


class TestGsResponseAfterStateTransitions(unittest.TestCase):
    """Step 7 – GS responses stay coherent with EvseStateEngine transitions."""

    def _gs_prefix(self, engine: EvseStateEngine) -> str:
        from open_evse_controller_sim.rapi_dispatch import RapiDispatcher
        from open_evse_controller_sim.rapi_parser import parse_frame
        d = RapiDispatcher(engine.model)
        resp = d.dispatch(parse_frame("$GS\r"))
        return resp

    def _gs_state_hex(self, engine: EvseStateEngine) -> str:
        """Return just the state hex field from a $GS response.

        GS format: $OK {state:02x} {elapsed} {pilot:02x} {vflags:04x}^{chk}\\r
        Splitting on whitespace gives ['$OK', '<state>', ...].
        """
        resp = self._gs_prefix(engine)
        return resp.split()[1]

    def test_gs_reflects_state_b(self) -> None:
        engine = EvseStateEngine()
        engine.set_vehicle_response(VehicleResponse.CONNECTED_IDLE)
        self.assertEqual(self._gs_state_hex(engine), "02")  # EVSE_STATE_B = 0x02

    def test_gs_reflects_state_c(self) -> None:
        engine = EvseStateEngine()
        engine.set_vehicle_response(VehicleResponse.CHARGING)
        self.assertEqual(self._gs_state_hex(engine), "03")  # EVSE_STATE_C = 0x03

    def test_gs_reflects_disabled(self) -> None:
        engine = EvseStateEngine()
        engine.disable()
        self.assertEqual(self._gs_state_hex(engine), "ff")  # EVSE_STATE_DISABLED = 0xFF

    def test_gs_reflects_gfi_fault(self) -> None:
        engine = EvseStateEngine()
        engine.inject_gfi_fault()
        self.assertEqual(self._gs_state_hex(engine), "06")  # EVSE_STATE_GFCI_FAULT = 0x06


if __name__ == "__main__":
    unittest.main()
