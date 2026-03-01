"""EVSE state model and state engine for simulator.

Field names and default values mirror firmware structures in
firmware/open_evse/J1772EvseController.h.

Steps 6, 7, 8:
  - EvseModel: plain dataclass with state fields (shared by RapiDispatcher)
  - EvseStateEngine: operator-facing state machine mirroring core transitions
    from J1772EvseController.cpp:1253-1601 plus fault injection.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from .fault_model import FaultModel

# ---------------------------------------------------------------------------
# State constants (J1772EvseController.h)
# ---------------------------------------------------------------------------
EVSE_STATE_UNKNOWN = 0x00
EVSE_STATE_A = 0x01          # vehicle state A 12V – not connected
EVSE_STATE_B = 0x02          # vehicle state B 9V – connected, ready
EVSE_STATE_C = 0x03          # vehicle state C 6V – charging
EVSE_STATE_D = 0x04          # vehicle state D 3V – vent required
EVSE_STATE_DIODE_CHK_FAILED = 0x05
EVSE_STATE_GFCI_FAULT = 0x06
EVSE_STATE_NO_GROUND = 0x07
EVSE_STATE_STUCK_RELAY = 0x08
# Firmware fault range: EVSE_STATE_D begins the range (J1772EvseController.h line 30).
# State D (vent required) is treated as a fault boundary in firmware Update() recovery
# logic even though it maps to a J1772 voltage level; the simulator preserves this
# so that _is_fault_state() and set_vehicle_response() blocking match firmware behavior.
EVSE_FAULT_STATE_BEGIN = EVSE_STATE_D    # first fault-range state
EVSE_FAULT_STATE_END = 0x0E             # last fault-range state
EVSE_STATE_SLEEPING = 0xFE
EVSE_STATE_DISABLED = 0xFF

# ---------------------------------------------------------------------------
# Volatile flag constants (J1772EvseController.h: ECVF_xxx)
# ---------------------------------------------------------------------------
ECVF_HARD_FAULT = 0x0002      # in non-autoresettable fault
ECVF_NOGND_TRIPPED = 0x0020   # no-ground tripped at least once
ECVF_CHARGING_ON = 0x0040     # charging relay is closed
ECVF_GFI_TRIPPED = 0x0080     # GFI tripped at least once since boot
ECVF_EV_CONNECTED = 0x0100    # EV connected (valid when pilot not N12)
ECVF_SESSION_ENDED = 0x0200   # used for charging session time calc

# Volatile flag defaults (ECVF_DEFAULT = ECVF_SESSION_ENDED)
_ECVF_DEFAULT = ECVF_SESSION_ENDED

# ---------------------------------------------------------------------------
# Pilot state constants (J1772Pilot.h enum)
# ---------------------------------------------------------------------------
PILOT_STATE_P12 = 0   # +12 V static (not connected)
PILOT_STATE_PWM = 1   # PWM duty-cycle (charging allowed)
PILOT_STATE_N12 = 2   # -12 V (diode check / fault)

# ---------------------------------------------------------------------------
# Current capacity limits (open_evse.h)
# ---------------------------------------------------------------------------
MIN_CURRENT_CAPACITY_J1772 = 6
MAX_CURRENT_CAPACITY_L1 = 24

# ---------------------------------------------------------------------------
# Debounce timing constants (open_evse.h: DELAY_STATE_TRANSITION_xxx)
# ---------------------------------------------------------------------------
# must stay within threshold for this time in ms before switching states
DELAY_STATE_TRANSITION_MS = 250
# must transition to state A from contacts closed in < 100 ms per spec;
# Leaf sometimes bounces 3→1 so debounced slightly anyway
DELAY_STATE_TRANSITION_A_MS = 25


# ---------------------------------------------------------------------------
# VehicleResponse – operator control abstraction (Step 7)
# ---------------------------------------------------------------------------

class VehicleResponse(IntEnum):
    """Simulated vehicle-side pilot interpretation.

    Maps to the J1772 pilot voltage levels the EV presents:
      DISCONNECTED   – EV not present     → State A (12 V, pilot P12)
      CONNECTED_IDLE – EV connected, idle → State B (9 V, pilot PWM)
      CHARGING       – EV ready to charge → State C (6 V, pilot PWM, relay closed)
    """
    DISCONNECTED = 0
    CONNECTED_IDLE = 1
    CHARGING = 2


# ---------------------------------------------------------------------------
# EvseModel – plain dataclass shared with RapiDispatcher
# ---------------------------------------------------------------------------

@dataclass
class EvseModel:
    # Core state visible via GS response
    evse_state: int = EVSE_STATE_A   # EVSE_STATE_A (not connected)
    pilot_state: int = PILOT_STATE_P12
    elapsed_charge_time: int = 0     # seconds, reported in GS
    vflags: int = _ECVF_DEFAULT      # volatile flags (ECVF_xxx), reported in GS

    # Settings visible via GE response
    enabled: bool = True
    current_capacity_amps: int = 16
    flags: int = 0x0000              # non-volatile flags (ECF_xxx), reported in GE
    svc_level: int = 2               # service level 1 or 2

    # Capacity range visible via GC response
    max_hw_current_capacity: int = 32


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _is_fault_state(state: int) -> bool:
    """Return True when *state* is in the firmware fault range."""
    return EVSE_FAULT_STATE_BEGIN <= state <= EVSE_FAULT_STATE_END


# ---------------------------------------------------------------------------
# EvseStateEngine – Steps 6, 7, 8
# ---------------------------------------------------------------------------

class EvseStateEngine:
    """Minimal EVSE state engine mirroring core firmware transitions.

    Step 6 – state transitions (J1772EvseController.cpp:1253-1601):
      Supports A/B/C normal states, disabled, sleeping, and fault placeholder
      states.  Debounce timing constants mirror open_evse.h values but are
      expressed as informational attributes only (the simulator ticks are
      driven by the GUI/test harness, not real-time ISR loops).

    Step 7 – operator controls:
      set_vehicle_response() abstracts the J1772 pilot-voltage interpretation
      so the operator panel maps directly to the same EVSE state fields that
      GS/GE/GC responses read.  enable(), disable(), sleep(), and
      set_current_capacity() complete the operator surface.

    Step 8 – fault injection:
      inject_gfi_fault(), inject_no_ground_fault(), inject_stuck_relay_fault(),
      and inject_diode_fault() set EVSE state and flag bits only; no
      low-level analog circuitry is emulated in MVP.  Fault naming and state
      values align with J1772EvseController.cpp:1348-1510.
    """

    # Debounce constants exposed for informational use / tests
    DELAY_STATE_TRANSITION_MS = DELAY_STATE_TRANSITION_MS
    DELAY_STATE_TRANSITION_A_MS = DELAY_STATE_TRANSITION_A_MS

    def __init__(self, model: EvseModel | None = None) -> None:
        self._model = model if model is not None else EvseModel()
        self._fault = FaultModel()

    @property
    def model(self) -> EvseModel:
        return self._model

    @property
    def fault(self) -> FaultModel:
        return self._fault

    # ------------------------------------------------------------------
    # Step 7: operator controls
    # ------------------------------------------------------------------

    def set_vehicle_response(self, response: VehicleResponse) -> None:
        """Set simulated vehicle response (operator panel control).

        Maps VehicleResponse to the EVSE state fields read by GS/GE/GC so
        responses remain coherent after the operator changes the vehicle state.

        Blocked when the EVSE is disabled, sleeping, or in a fault state –
        mirroring firmware Update() early-return paths.
        """
        m = self._model
        if m.evse_state in (EVSE_STATE_DISABLED, EVSE_STATE_SLEEPING):
            return
        if _is_fault_state(m.evse_state):
            return

        if response == VehicleResponse.DISCONNECTED:
            m.evse_state = EVSE_STATE_A
            m.pilot_state = PILOT_STATE_P12
            m.vflags &= ~ECVF_EV_CONNECTED
            m.vflags &= ~ECVF_CHARGING_ON
        elif response == VehicleResponse.CONNECTED_IDLE:
            m.evse_state = EVSE_STATE_B
            m.pilot_state = PILOT_STATE_PWM
            m.vflags |= ECVF_EV_CONNECTED
            m.vflags &= ~ECVF_CHARGING_ON
        elif response == VehicleResponse.CHARGING:
            m.evse_state = EVSE_STATE_C
            m.pilot_state = PILOT_STATE_PWM
            m.vflags |= ECVF_EV_CONNECTED
            m.vflags |= ECVF_CHARGING_ON

    def enable(self) -> None:
        """Enable EVSE – mirrors FE / g_EvseController.Enable().

        Transitions DISABLED or SLEEPING back to state A and sets
        enabled=True, keeping the model coherent with GE responses.
        """
        m = self._model
        m.enabled = True
        if m.evse_state in (EVSE_STATE_DISABLED, EVSE_STATE_SLEEPING):
            m.evse_state = EVSE_STATE_A
            m.pilot_state = PILOT_STATE_P12

    def disable(self) -> None:
        """Disable EVSE – mirrors FD / g_EvseController.Disable().

        Sets state to DISABLED and opens the relay (clears ECVF_CHARGING_ON).
        """
        m = self._model
        m.enabled = False
        m.evse_state = EVSE_STATE_DISABLED
        m.vflags &= ~ECVF_CHARGING_ON

    def sleep(self) -> None:
        """Put EVSE to sleep (timer/limit sleep, mirrors EVSE_STATE_SLEEPING).

        Opens the relay (clears ECVF_CHARGING_ON).
        """
        m = self._model
        m.evse_state = EVSE_STATE_SLEEPING
        m.vflags &= ~ECVF_CHARGING_ON

    def set_current_capacity(self, amps: int) -> None:
        """Set charge current setpoint with firmware-compatible clamping.

        Mirrors SetCurrentCapacity() clamping: min = MIN_CURRENT_CAPACITY_J1772,
        max = max_hw_current_capacity for L2 else MAX_CURRENT_CAPACITY_L1.
        The model field is updated in-place so GC/GE responses stay coherent.
        """
        m = self._model
        effective_max = (
            m.max_hw_current_capacity if m.svc_level == 2 else MAX_CURRENT_CAPACITY_L1
        )
        m.current_capacity_amps = max(MIN_CURRENT_CAPACITY_J1772, min(amps, effective_max))

    # ------------------------------------------------------------------
    # Step 8: fault injection
    # ------------------------------------------------------------------

    def inject_gfi_fault(self) -> None:
        """Inject a GFI/GFCI fault (EVSE_STATE_GFCI_FAULT = 0x06).

        Sets ECVF_HARD_FAULT and ECVF_GFI_TRIPPED volatile flags; opens
        the relay.  Mirrors J1772EvseController.cpp GFI fault entry path.
        """
        m = self._model
        self._fault.gfi_trip = True
        m.evse_state = EVSE_STATE_GFCI_FAULT
        m.vflags |= ECVF_HARD_FAULT
        m.vflags |= ECVF_GFI_TRIPPED
        m.vflags &= ~ECVF_CHARGING_ON

    def inject_no_ground_fault(self) -> None:
        """Inject a no-ground fault (EVSE_STATE_NO_GROUND = 0x07).

        Sets ECVF_HARD_FAULT and ECVF_NOGND_TRIPPED; opens the relay.
        Mirrors J1772EvseController.cpp ADVPWR ground check failure path.
        """
        m = self._model
        self._fault.no_ground = True
        m.evse_state = EVSE_STATE_NO_GROUND
        m.vflags |= ECVF_HARD_FAULT
        m.vflags |= ECVF_NOGND_TRIPPED
        m.vflags &= ~ECVF_CHARGING_ON

    def inject_stuck_relay_fault(self) -> None:
        """Inject a stuck-relay fault (EVSE_STATE_STUCK_RELAY = 0x08).

        Sets ECVF_HARD_FAULT; opens the relay.
        Mirrors J1772EvseController.cpp stuck-relay detection path.
        """
        m = self._model
        self._fault.stuck_relay = True
        m.evse_state = EVSE_STATE_STUCK_RELAY
        m.vflags |= ECVF_HARD_FAULT
        m.vflags &= ~ECVF_CHARGING_ON

    def inject_diode_fault(self) -> None:
        """Inject a diode-check fault (EVSE_STATE_DIODE_CHK_FAILED = 0x05).

        Sets ECVF_HARD_FAULT; opens the relay.
        Mirrors J1772EvseController.cpp DiodeCheckEnabled() failure path.
        """
        m = self._model
        self._fault.diode_fault = True
        m.evse_state = EVSE_STATE_DIODE_CHK_FAILED
        m.vflags |= ECVF_HARD_FAULT
        m.vflags &= ~ECVF_CHARGING_ON

    def clear_fault(self) -> None:
        """Clear any active fault and return to state A.

        Mirrors firmware recovery: after fault cleared, pilot returns to P12
        and EVSE transitions back to state A (not connected).
        Resets all FaultModel flags.
        """
        m = self._model
        self._fault.gfi_trip = False
        self._fault.no_ground = False
        self._fault.stuck_relay = False
        self._fault.diode_fault = False
        m.evse_state = EVSE_STATE_A
        m.pilot_state = PILOT_STATE_P12
        m.vflags &= ~ECVF_HARD_FAULT
        m.vflags &= ~ECVF_EV_CONNECTED
        m.vflags &= ~ECVF_CHARGING_ON

