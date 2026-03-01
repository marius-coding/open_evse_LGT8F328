"""Minimal EVSE state model placeholder."""

from dataclasses import dataclass


@dataclass
class EvseModel:
    evse_state: int = 1
    pilot_state: int = 1
    enabled: bool = True
    current_capacity_amps: int = 16

