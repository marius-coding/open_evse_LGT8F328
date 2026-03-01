"""UART transport adapter placeholder for simulator workspace."""


class UartTransport:
    def __init__(self, port: str, baudrate: int = 115200) -> None:
        self.port = port
        self.baudrate = baudrate

