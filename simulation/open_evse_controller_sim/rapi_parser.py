"""Step 3: strict RAPI framing/parsing/serialization modeled from AVR firmware."""

from dataclasses import dataclass
from typing import Optional

from .rapi_contract import (
    ESRAPI_BUFLEN,
    ESRAPI_EOC,
    ESRAPI_MAX_ARGS,
    ESRAPI_SOC,
    ESRAPI_SOS,
    INVALID_SEQUENCE_ID,
)


def _htou8(hex_text: str) -> int:
    """Mirror AVR htou8(): parse first 2 chars, return 0 on invalid."""
    value = 0
    for i in range(2):
        if i >= len(hex_text):
            break
        c = hex_text[i]
        if i == 1:
            value <<= 4
        if "0" <= c <= "9":
            value += ord(c) - ord("0")
        elif "A" <= c <= "F":
            value += ord(c) - ord("A") + 10
        elif "a" <= c <= "f":
            value += ord(c) - ord("a") + 10
        else:
            return 0
    return value & 0xFF


def _checksum_xor(payload: str) -> int:
    chk = 0
    for c in payload:
        chk ^= ord(c)
    return chk & 0xFF


@dataclass(frozen=True)
class ParsedRapiFrame:
    raw: str
    token: str
    args: tuple[str, ...]
    checksum_type: str  # "none" | "additive" | "xor"
    sequence_id: int  # 0 means invalid/absent, mirrors firmware


def append_sequence_id(base: str, seq_id: int) -> str:
    return f"{base} {ESRAPI_SOS}{seq_id:02X}"


def append_xor_checksum(base: str) -> str:
    return f"{base}^{_checksum_xor(base):02X}{ESRAPI_EOC}"


def build_response(ok: bool, payload: str = "", sequence_id: int = INVALID_SEQUENCE_ID) -> str:
    text = f"{ESRAPI_SOC}{'OK' if ok else 'NK'}"
    if payload:
        text += f" {payload}"
    if sequence_id != INVALID_SEQUENCE_ID:
        text = append_sequence_id(text, sequence_id)
    return append_xor_checksum(text)


def _tokenize_command(core: str) -> Optional[tuple[list[str], str]]:
    if not core.startswith(ESRAPI_SOC):
        return None
    if len(core) < 2:
        return None

    body = core[1:]
    first = body[0] if body else "\x00"
    achk_sum = (ord(ESRAPI_SOC) + ord(first)) & 0xFF
    xchk_sum = (ord(ESRAPI_SOC) ^ ord(first)) & 0xFF
    chktype = "none"
    hchk_sum = 0
    token_cnt = 1
    pre_chk = body

    i = 1
    while i < len(body):
        c = body[i]
        if c == " ":
            if token_cnt >= ESRAPI_MAX_ARGS:
                return None
            achk_sum = (achk_sum + ord(c)) & 0xFF
            xchk_sum = (xchk_sum ^ ord(c)) & 0xFF
            token_cnt += 1
            i += 1
        elif c in ("*", "^"):
            chktype = "additive" if c == "*" else "xor"
            hchk_sum = _htou8(body[i + 1 : i + 3])
            pre_chk = body[:i]
            break
        else:
            achk_sum = (achk_sum + ord(c)) & 0xFF
            xchk_sum = (xchk_sum ^ ord(c)) & 0xFF
            i += 1

    if chktype == "additive" and hchk_sum != achk_sum:
        return None
    if chktype == "xor" and hchk_sum != xchk_sum:
        return None

    tokens = pre_chk.split(" ")
    return tokens, chktype


def parse_frame(frame: str) -> Optional[ParsedRapiFrame]:
    """Parse one complete '$...\\r' frame; return None on failure."""
    if not frame.endswith(ESRAPI_EOC):
        return None
    core = frame[:-1]
    tokenized = _tokenize_command(core)
    if tokenized is None:
        return None
    tokens, checksum_type = tokenized
    if not tokens:
        return None

    seq = INVALID_SEQUENCE_ID
    if len(tokens) > 1 and tokens[-1].startswith(ESRAPI_SOS):
        seq = _htou8(tokens[-1][1:])
        tokens = tokens[:-1]
    if not tokens:
        return None

    return ParsedRapiFrame(
        raw=frame,
        token=tokens[0],
        args=tuple(tokens[1:]),
        checksum_type=checksum_type,
        sequence_id=seq,
    )


class RapiStreamParser:
    """Stateful stream parser modeled after EvseRapiProcessor::doCmd()."""

    def __init__(self) -> None:
        self._buffer = ""

    def feed(self, data: str) -> list[ParsedRapiFrame]:
        out: list[ParsedRapiFrame] = []
        for c in data:
            if c == ESRAPI_SOC:
                self._buffer = ESRAPI_SOC
            elif self._buffer.startswith(ESRAPI_SOC):
                if len(self._buffer) < ESRAPI_BUFLEN - 1:
                    if c == ESRAPI_EOC:
                        parsed = parse_frame(self._buffer + ESRAPI_EOC)
                        if parsed is not None:
                            out.append(parsed)
                        self._buffer = ""
                    else:
                        self._buffer += c
                else:
                    self._buffer = ""
        return out

