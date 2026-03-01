"""Fault state placeholder for simulator."""

from dataclasses import dataclass


@dataclass
class FaultModel:
    gfi_trip: bool = False
    no_ground: bool = False
    stuck_relay: bool = False
    diode_fault: bool = False

