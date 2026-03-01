"""Minimal EVSE state model for simulator.

Field names and default values mirror firmware structures in
firmware/open_evse/J1772EvseController.h.
"""

from dataclasses import dataclass

# Volatile flag defaults (J1772EvseController.h: ECVF_DEFAULT = ECVF_SESSION_ENDED = 0x0200)
_ECVF_DEFAULT = 0x0200


@dataclass
class EvseModel:
    # Core state visible via GS response
    evse_state: int = 0x01           # EVSE_STATE_A (not connected)
    pilot_state: int = 0             # PILOT_STATE_P12
    elapsed_charge_time: int = 0     # seconds, reported in GS
    vflags: int = _ECVF_DEFAULT      # volatile flags (ECVF_xxx), reported in GS

    # Settings visible via GE response
    enabled: bool = True
    current_capacity_amps: int = 16
    flags: int = 0x0000              # non-volatile flags (ECF_xxx), reported in GE
    svc_level: int = 2               # service level 1 or 2

    # Capacity range visible via GC response
    max_hw_current_capacity: int = 32

