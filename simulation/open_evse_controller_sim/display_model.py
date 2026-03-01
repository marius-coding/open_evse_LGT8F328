"""Display simulation model placeholder."""

from dataclasses import dataclass


@dataclass
class DisplayModel:
    line1: str = "OpenEVSE"
    line2: str = "Ready"
    color: str = "GREEN"

