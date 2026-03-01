"""RAPI dispatch surface for simulator."""

from .rapi_contract import MVP_COMMANDS


class RapiDispatcher:
    def __init__(self) -> None:
        self.supported_commands = set(MVP_COMMANDS)

