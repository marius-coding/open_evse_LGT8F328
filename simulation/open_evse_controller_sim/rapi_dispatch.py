"""Step 5: RAPI command handlers for MVP ESP debugging command set.

Handlers mirror firmware EvseRapiProcessor::processCmd() for the commands
listed in the MVP matrix (rapi_contract.py):

  GV, GS, GE, GC, G0  – get-parameter handlers
  SC, FE, FD, SL       – set/function handlers

Async notification builders mirror firmware:
  AB – sendBootNotification()   (rapi_proc.cpp:151-162)
  AT – sendEvseState()          (rapi_proc.cpp:164-173)

Firmware constant sources:
  firmware/open_evse/open_evse.h  : VERSION "8.2.3", SERIAL_BAUD, state macros
  firmware/open_evse/rapi_proc.h  : RAPIVER "5.2.1-LGT"
  firmware/open_evse/J1772EvseController.h : EVSE_STATE_xxx, ECF_xxx, ECVF_xxx
"""

from __future__ import annotations

from .evse_model import EvseModel
from .rapi_contract import MVP_COMMANDS
from .rapi_parser import ParsedRapiFrame, append_xor_checksum, build_response

# Firmware version strings
FW_VERSION = "8.2.3"       # open_evse.h: #define VERSION
RAPI_VERSION = "5.2.1-LGT"  # rapi_proc.h: #define RAPIVER

# Current capacity limits (open_evse.h)
MIN_CURRENT_CAPACITY = 6    # MIN_CURRENT_CAPACITY_J1772
MAX_CURRENT_CAPACITY_L1 = 24
MAX_CURRENT_CAPACITY_L2 = 80

# Pilot state values matching the firmware enum (J1772Pilot.h)
#   enum { PILOT_STATE_P12, PILOT_STATE_PWM, PILOT_STATE_N12 } PILOT_STATE;
PILOT_STATE_P12 = 0
PILOT_STATE_PWM = 1
PILOT_STATE_N12 = 2

# EVSE state constants (J1772EvseController.h)
EVSE_STATE_A = 0x01
EVSE_STATE_SLEEPING = 0xFE
EVSE_STATE_DISABLED = 0xFF

# Volatile flag indicating EV is connected (J1772EvseController.h: ECVF_EV_CONNECTED)
ECVF_EV_CONNECTED = 0x0100


class RapiDispatcher:
    """Dispatch parsed RAPI frames to simulator state handlers.

    Args:
        model: Shared EVSE state model mutated by set-commands.
                A default EvseModel() is created when not provided.
    """

    def __init__(self, model: EvseModel | None = None) -> None:
        self.supported_commands = set(MVP_COMMANDS)
        self._model = model if model is not None else EvseModel()

    @property
    def model(self) -> EvseModel:
        return self._model

    def dispatch(self, frame: ParsedRapiFrame) -> str:
        """Dispatch *frame* and return the complete RAPI response string."""
        cmd = frame.token
        if cmd not in self.supported_commands:
            return build_response(False, sequence_id=frame.sequence_id)
        handler = getattr(self, f"_handle_{cmd}", None)
        if handler is None:
            return build_response(False, sequence_id=frame.sequence_id)
        return handler(frame)

    # ------------------------------------------------------------------
    # GET handlers
    # ------------------------------------------------------------------

    def _handle_GV(self, frame: ParsedRapiFrame) -> str:
        """GV – get firmware version and RAPI protocol version.

        Firmware (rapi_proc.cpp:798-802):
          GetVerStr(buffer); strcat(buffer," "); strcat_P(buffer,RAPI_VER)
        Response: $OK {FW_VERSION} {RAPI_VERSION}^{chk}\\r
        """
        payload = f"{FW_VERSION} {RAPI_VERSION}"
        return build_response(True, payload, frame.sequence_id)

    def _handle_GS(self, frame: ParsedRapiFrame) -> str:
        """GS – get EVSE state.

        Firmware (rapi_proc.cpp:775-779):
          sprintf(buffer,"%02x %ld %02x %04x",
                  state, elapsed_charge_time, pilot_state, vflags)
        Response: $OK {state:02x} {elapsed_s} {pilot_state:02x} {vflags:04x}^{chk}\\r
        """
        m = self._model
        payload = (
            f"{m.evse_state:02x} {m.elapsed_charge_time}"
            f" {m.pilot_state:02x} {m.vflags:04x}"
        )
        return build_response(True, payload, frame.sequence_id)

    def _handle_GE(self, frame: ParsedRapiFrame) -> str:
        """GE – get settings.

        Firmware (rapi_proc.cpp:700-703):
          sprintf(buffer,"%d %04x", current_capacity, flags)
        Response: $OK {current_capacity} {flags:04x}^{chk}\\r
        """
        m = self._model
        payload = f"{m.current_capacity_amps} {m.flags:04x}"
        return build_response(True, payload, frame.sequence_id)

    def _handle_GC(self, frame: ParsedRapiFrame) -> str:
        """GC – get current capacity range.

        Firmware (rapi_proc.cpp:648-659):
          min = MIN_CURRENT_CAPACITY_J1772
          max = GetMaxHwCurrentCapacity() for L2 else MAX_CURRENT_CAPACITY_L1
          cur = GetCurrentCapacity()
          cap = GetMaxCurrentCapacity()
          sprintf(buffer,"%d %d %d %d", min, max, cur, cap)
        Response: $OK {min} {effective_max} {current} {effective_max}^{chk}\\r
        """
        m = self._model
        effective_max = (
            m.max_hw_current_capacity
            if m.svc_level == 2
            else MAX_CURRENT_CAPACITY_L1
        )
        payload = (
            f"{MIN_CURRENT_CAPACITY} {effective_max}"
            f" {m.current_capacity_amps} {effective_max}"
        )
        return build_response(True, payload, frame.sequence_id)

    def _handle_G0(self, frame: ParsedRapiFrame) -> str:
        """G0 – get EV connect state.

        Firmware (rapi_proc.cpp:602-614):
          if pilot_state == PILOT_STATE_N12 → connstate = 2 (unknown)
          elif EvConnected()                → connstate = 1
          else                              → connstate = 0
        Response: $OK {0|1|2}^{chk}\\r
        """
        m = self._model
        if m.pilot_state == PILOT_STATE_N12:
            connstate = 2
        elif bool(m.vflags & ECVF_EV_CONNECTED):
            connstate = 1
        else:
            connstate = 0
        return build_response(True, str(connstate), frame.sequence_id)

    # ------------------------------------------------------------------
    # SET / FUNCTION handlers
    # ------------------------------------------------------------------

    def _handle_SC(self, frame: ParsedRapiFrame) -> str:
        """SC – set current capacity.

        Firmware (rapi_proc.cpp:461-512):
          SetCurrentCapacity(amps); sprintf(buffer,"%d",GetCurrentCapacity())
        Accepts: $SC {amps}\\r  or  $SC {amps} V\\r (volatile, ignored in MVP)
        Response: $OK {applied_amps}^{chk}\\r  or  $NK on bad args.
        """
        if not frame.args:
            return build_response(False, sequence_id=frame.sequence_id)
        try:
            amps = int(frame.args[0])
        except ValueError:
            return build_response(False, sequence_id=frame.sequence_id)
        amps = max(MIN_CURRENT_CAPACITY, min(amps, self._model.max_hw_current_capacity))
        self._model.current_capacity_amps = amps
        return build_response(True, str(amps), frame.sequence_id)

    def _handle_FE(self, frame: ParsedRapiFrame) -> str:
        """FE – enable EVSE.

        Firmware (rapi_proc.cpp:300-302): g_EvseController.Enable()
        Transitions DISABLED/SLEEPING back to state A.
        Response: $OK^{chk}\\r
        """
        m = self._model
        m.enabled = True
        if m.evse_state in (EVSE_STATE_SLEEPING, EVSE_STATE_DISABLED):
            m.evse_state = EVSE_STATE_A
        return build_response(True, sequence_id=frame.sequence_id)

    def _handle_FD(self, frame: ParsedRapiFrame) -> str:
        """FD – disable EVSE.

        Firmware (rapi_proc.cpp:297-299): g_EvseController.Disable()
        Response: $OK^{chk}\\r
        """
        m = self._model
        m.enabled = False
        m.evse_state = EVSE_STATE_DISABLED
        return build_response(True, sequence_id=frame.sequence_id)

    def _handle_SL(self, frame: ParsedRapiFrame) -> str:
        """SL – set service level.

        Firmware (rapi_proc.cpp:513-535): SetSvcLevel(level, 1)
        Accepts: $SL 1\\r or $SL 2\\r  ('A' auto mode not in MVP)
        Response: $OK^{chk}\\r  or  $NK on bad args.
        """
        if not frame.args or frame.args[0] not in ("1", "2"):
            return build_response(False, sequence_id=frame.sequence_id)
        self._model.svc_level = int(frame.args[0])
        return build_response(True, sequence_id=frame.sequence_id)

    # ------------------------------------------------------------------
    # Async notification builders
    # These are sent spontaneously (not as command responses).
    # ------------------------------------------------------------------

    def build_boot_notification(self) -> str:
        """Build an AB (boot) notification frame.

        Firmware (rapi_proc.cpp:151-162):
          sprintf(g_sTmp,"%cAB %02x ", SOC, state); GetVerStr(s); appendChk()
        Format: $AB {state:02x} {FW_VERSION}^{chk}\\r
        """
        m = self._model
        base = f"$AB {m.evse_state:02x} {FW_VERSION}"
        return append_xor_checksum(base)

    def build_state_notification(self) -> str:
        """Build an AT (state-change) notification frame.

        Firmware (rapi_proc.cpp:164-173):
          sprintf(g_sTmp,"%cAT %02x %02x %d %04x",
                  SOC, state, pilot_state, current_capacity, vflags)
        Format: $AT {state:02x} {pilot_state:02x} {current_capacity} {vflags:04x}^{chk}\\r
        """
        m = self._model
        base = (
            f"$AT {m.evse_state:02x} {m.pilot_state:02x}"
            f" {m.current_capacity_amps} {m.vflags:04x}"
        )
        return append_xor_checksum(base)

