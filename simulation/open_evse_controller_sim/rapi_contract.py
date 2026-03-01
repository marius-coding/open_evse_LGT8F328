"""Step 1: firmware-derived simulator behavior contract and MVP matrix."""

from dataclasses import dataclass

ESRAPI_BUFLEN = 32
ESRAPI_MAX_ARGS = 10
ESRAPI_SOC = "$"
ESRAPI_EOC = "\r"
ESRAPI_SOS = ":"
INVALID_SEQUENCE_ID = 0


@dataclass(frozen=True)
class SourceAnchor:
    file: str
    focus: str


CONTRACT_SOURCES = (
    SourceAnchor("firmware/open_evse/rapi_proc.h", "RAPI command/response framing and checksums"),
    SourceAnchor("firmware/open_evse/rapi_proc.cpp", "doCmd/tokenize/response behavior"),
    SourceAnchor("firmware/open_evse/J1772EvseController.h", "state and controller fields"),
    SourceAnchor("firmware/open_evse/J1772EvseController.cpp", "state transition behavior"),
)

# MVP command/event surface frozen for initial ESP debugging milestone.
MVP_COMMANDS = ("GV", "GS", "GE", "GC", "G0", "SC", "FE", "FD", "SL")
MVP_ASYNC_EVENTS = ("AB", "AT")

