"""PySide6 interactive simulator window.

PySide6 is imported lazily inside :func:`build_gui` so that the rest of the
simulator (including tests) can be imported without a display server or
PySide6 installed.  Install it with ``pip install pyside6`` before calling
``build_gui()``.

The window renders a 16x2 simulated LCD, interactive EV/operator controls,
optional live serial connectivity to an ESP target, and a RAPI RX/TX monitor.
State mutations are applied through
:class:`~open_evse_controller_sim.evse_model.EvseStateEngine` and reflected in
the display model.

The UI uses Qt layouts and a QSplitter so it scales automatically with the
window size and the system DPI / screen resolution.  Qt 6 (PySide6) enables
high-DPI scaling by default; no additional configuration is required.
"""

from __future__ import annotations

import time

from .display_model import (
    LCD_BLUE,
    LCD_GREEN,
    LCD_RED,
    LCD_TEAL,
    LCD_VIOLET,
    LCD_WHITE,
    LCD_YELLOW,
    DisplayModel,
)
from .evse_model import EvseStateEngine, VehicleResponse
from .rapi_dispatch import RapiDispatcher
from .simulator_app import SimulatorApp
from .transport_uart import SERIAL_BAUD, UartTransport

# Mapping from firmware LCD colour integers to CSS rgba() strings.
# Hue choices follow standard J1772 / Adafruit RGB LCD conventions.
_COLOUR_MAP: dict[int, str] = {
    LCD_RED:    "rgba(220,  50,  50, 200)",
    LCD_GREEN:  "rgba( 50, 160,  50, 200)",
    LCD_YELLOW: "rgba(200, 180,  40, 200)",
    LCD_BLUE:   "rgba( 50,  50, 200, 200)",
    LCD_VIOLET: "rgba(140,  40, 180, 200)",
    LCD_TEAL:   "rgba( 40, 180, 160, 200)",
    LCD_WHITE:  "rgba(200, 200, 200, 200)",
}
_DEFAULT_COLOUR: str = "rgba(100, 100, 100, 200)"

# Human-readable descriptions for RAPI command/response tokens.
_RAPI_CMD_DESC: dict[str, str] = {
    "GV": "Get firmware / RAPI version",
    "GS": "Get EVSE state",
    "GE": "Get settings (capacity & flags)",
    "GC": "Get current capacity range",
    "G0": "Get EV connect state",
    "SC": "Set current capacity",
    "FE": "Enable EVSE",
    "FD": "Disable EVSE",
    "SL": "Set service level",
    "AB": "Boot notification (async)",
    "AT": "State-change notification (async)",
    "OK": "Response: success",
    "NK": "Response: error / unknown command",
}


def _describe_rapi(text: str) -> str:
    """Return a human-readable description for a raw RAPI frame string."""
    stripped = text.strip()
    if not stripped.startswith("$"):
        return ""
    word = stripped[1:].split()[0] if stripped[1:].split() else ""
    token = word.split("^")[0].split("*")[0]
    return _RAPI_CMD_DESC.get(token, f"Command: {token}")


_VEHICLE_CHOICES = {
    "Disconnected": VehicleResponse.DISCONNECTED,
    "Connected idle": VehicleResponse.CONNECTED_IDLE,
    "Charging": VehicleResponse.CHARGING,
}


def build_gui(
    engine: EvseStateEngine | None = None,
    *,
    port: str | None = None,
    baudrate: int = SERIAL_BAUD,
    send_boot_notification: bool = True,
) -> None:
    """Build and run the PySide6 simulator window.

    Creates a display panel showing the 16x2 LCD simulation driven by
    *engine*.  If *engine* is ``None`` a default
    :class:`~open_evse_controller_sim.evse_model.EvseStateEngine` is used.

    The window uses Qt layouts and scales automatically with the window size
    and system DPI / screen resolution.

    The call blocks until the user closes the window.

    Raises:
        ImportError: propagated from ``import PySide6`` when the package is
            not installed.  Install with ``pip install pyside6``.
    """
    try:
        from PySide6.QtCore import Qt, QTimer  # type: ignore[import]
        from PySide6.QtGui import QFont  # type: ignore[import]
        from PySide6.QtWidgets import (  # type: ignore[import]
            QApplication,
            QButtonGroup,
            QFrame,
            QGroupBox,
            QHBoxLayout,
            QHeaderView,
            QLabel,
            QLineEdit,
            QPushButton,
            QRadioButton,
            QScrollArea,
            QSizePolicy,
            QSlider,
            QSpinBox,
            QSplitter,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
            QWidget,
            QComboBox,
        )
    except ImportError as exc:
        raise ImportError(
            "PySide6 is required for build_gui(); install it with: pip install pyside6"
        ) from exc

    import sys

    if engine is None:
        engine = EvseStateEngine()

    display = DisplayModel()
    display.update_from_evse_state(engine.model)

    dispatcher = RapiDispatcher(engine.model)
    _app_state: dict = {"app": None, "transport": None}
    max_log_lines = 400

    # ------------------------------------------------------------------
    # QApplication (create only if no instance already exists)
    # ------------------------------------------------------------------
    qt_app = QApplication.instance()
    if qt_app is None:
        # Qt 6 (PySide6) enables high-DPI scaling automatically; no
        # additional attributes are required.
        qt_app = QApplication(sys.argv)

    # ------------------------------------------------------------------
    # Main window
    # ------------------------------------------------------------------
    window = QWidget()
    window.setWindowTitle("OpenEVSE Interactive Simulator")
    window.setMinimumSize(800, 540)
    window.resize(1100, 740)

    root_layout = QVBoxLayout(window)
    root_layout.setContentsMargins(8, 8, 8, 8)

    splitter = QSplitter(Qt.Horizontal)
    splitter.setChildrenCollapsible(False)
    root_layout.addWidget(splitter)

    # ==================== LEFT PANEL ==================================
    left_widget = QWidget()
    left_layout = QVBoxLayout(left_widget)
    left_layout.setAlignment(Qt.AlignTop)

    # --- Connection group ---
    conn_group = QGroupBox("Connection")
    conn_layout = QVBoxLayout(conn_group)

    port_row = QHBoxLayout()
    port_label = QLabel("Serial port:")
    port_input = QLineEdit(port or "")
    port_input.setPlaceholderText("/dev/ttyUSB0 or COM3")
    port_row.addWidget(port_label)
    port_row.addWidget(port_input)
    conn_layout.addLayout(port_row)

    baud_row = QHBoxLayout()
    baud_label = QLabel("Baud rate:")
    baud_input = QSpinBox()
    baud_input.setRange(1200, 3000000)
    baud_input.setValue(baudrate)
    baud_input.setSingleStep(9600)
    baud_row.addWidget(baud_label)
    baud_row.addWidget(baud_input)
    conn_layout.addLayout(baud_row)

    btn_row = QHBoxLayout()
    connect_btn = QPushButton("Connect")
    disconnect_btn = QPushButton("Disconnect")
    btn_row.addWidget(connect_btn)
    btn_row.addWidget(disconnect_btn)
    conn_layout.addLayout(btn_row)

    conn_status = QLabel("Disconnected")
    conn_status.setStyleSheet("font-style: italic;")
    conn_layout.addWidget(conn_status)

    left_layout.addWidget(conn_group)

    # --- EV Controls group ---
    ev_group = QGroupBox("EV Controls")
    ev_layout = QVBoxLayout(ev_group)

    vehicle_row = QHBoxLayout()
    vehicle_label = QLabel("Vehicle:")
    vehicle_combo = QComboBox()
    vehicle_combo.addItems(list(_VEHICLE_CHOICES.keys()))
    vehicle_row.addWidget(vehicle_label)
    vehicle_row.addWidget(vehicle_combo)
    ev_layout.addLayout(vehicle_row)

    svc_row = QHBoxLayout()
    svc_label = QLabel("Service level:")
    svc_btn_group = QButtonGroup()
    svc_radio_1 = QRadioButton("1")
    svc_radio_2 = QRadioButton("2")
    svc_btn_group.addButton(svc_radio_1, 1)
    svc_btn_group.addButton(svc_radio_2, 2)
    if engine.model.svc_level == 1:
        svc_radio_1.setChecked(True)
    else:
        svc_radio_2.setChecked(True)
    svc_row.addWidget(svc_label)
    svc_row.addWidget(svc_radio_1)
    svc_row.addWidget(svc_radio_2)
    svc_row.addStretch()
    ev_layout.addLayout(svc_row)

    current_row = QHBoxLayout()
    current_label = QLabel("Current (A):")
    current_slider = QSlider(Qt.Horizontal)
    current_slider.setRange(6, 80)
    current_slider.setValue(engine.model.current_capacity_amps)
    current_slider.setTickInterval(5)
    current_slider.setTickPosition(QSlider.TicksBelow)
    current_value_label = QLabel(str(engine.model.current_capacity_amps))
    current_value_label.setMinimumWidth(30)
    current_row.addWidget(current_label)
    current_row.addWidget(current_slider, stretch=1)
    current_row.addWidget(current_value_label)
    ev_layout.addLayout(current_row)

    state_btn_row = QHBoxLayout()
    enable_btn = QPushButton("Enable")
    disable_btn = QPushButton("Disable")
    sleep_btn = QPushButton("Sleep")
    state_btn_row.addWidget(enable_btn)
    state_btn_row.addWidget(disable_btn)
    state_btn_row.addWidget(sleep_btn)
    ev_layout.addLayout(state_btn_row)

    left_layout.addWidget(ev_group)

    # --- Fault Injection group ---
    fault_group = QGroupBox("Fault Injection")
    fault_layout = QVBoxLayout(fault_group)

    fault_row1 = QHBoxLayout()
    gfi_btn = QPushButton("GFI")
    nognd_btn = QPushButton("No Ground")
    stuck_btn = QPushButton("Stuck Relay")
    fault_row1.addWidget(gfi_btn)
    fault_row1.addWidget(nognd_btn)
    fault_row1.addWidget(stuck_btn)
    fault_layout.addLayout(fault_row1)

    fault_row2 = QHBoxLayout()
    diode_btn = QPushButton("Diode Fault")
    clear_btn = QPushButton("Clear Fault")
    fault_row2.addWidget(diode_btn)
    fault_row2.addWidget(clear_btn)
    fault_row2.addStretch()
    fault_layout.addLayout(fault_row2)

    left_layout.addWidget(fault_group)

    # --- State Snapshot group ---
    snap_group = QGroupBox("State Snapshot")
    snap_layout = QVBoxLayout(snap_group)

    def _make_kv_row(key: str) -> tuple[QHBoxLayout, QLabel]:
        row = QHBoxLayout()
        lbl_key = QLabel(f"{key}:")
        lbl_key.setMinimumWidth(90)
        lbl_val = QLabel("—")
        lbl_val.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row.addWidget(lbl_key)
        row.addWidget(lbl_val)
        row.addStretch()
        snap_layout.addLayout(row)
        return row, lbl_val

    _, lbl_state   = _make_kv_row("EVSE state")
    _, lbl_pilot   = _make_kv_row("Pilot")
    _, lbl_current = _make_kv_row("Current (A)")
    _, lbl_flags   = _make_kv_row("Flags")
    _, lbl_vflags  = _make_kv_row("VFlags")

    left_layout.addWidget(snap_group)
    left_layout.addStretch()

    splitter.addWidget(left_widget)

    # ==================== RIGHT PANEL =================================
    right_widget = QWidget()
    right_layout = QVBoxLayout(right_widget)

    # --- LCD Display group ---
    lcd_group = QGroupBox("LCD Display")
    lcd_layout = QVBoxLayout(lcd_group)

    lcd_frame = QFrame()
    lcd_frame.setFrameShape(QFrame.Box)
    lcd_frame.setLineWidth(2)
    lcd_frame_layout = QVBoxLayout(lcd_frame)
    lcd_frame_layout.setContentsMargins(12, 8, 12, 8)

    mono_font = QFont("Courier New", 16)
    mono_font.setBold(True)
    lcd_line1 = QLabel(display.line1)
    lcd_line2 = QLabel(display.line2)
    for lbl in (lcd_line1, lcd_line2):
        lbl.setFont(mono_font)
        lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        lbl.setMinimumHeight(30)
        lcd_frame_layout.addWidget(lbl)

    lcd_layout.addWidget(lcd_frame)
    right_layout.addWidget(lcd_group)

    # --- RAPI Traffic group ---
    rapi_group = QGroupBox("RAPI Traffic")
    rapi_layout = QVBoxLayout(rapi_group)

    rapi_table = QTableWidget(0, 2)
    rapi_table.setHorizontalHeaderLabels(["Frame", "Description"])
    rapi_table.horizontalHeader().setStretchLastSection(True)
    rapi_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
    rapi_table.verticalHeader().setVisible(False)
    rapi_table.setEditTriggers(QTableWidget.NoEditTriggers)
    rapi_table.setSelectionBehavior(QTableWidget.SelectRows)
    rapi_table.setAlternatingRowColors(True)
    rapi_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    rapi_layout.addWidget(rapi_table)

    right_layout.addWidget(rapi_group, stretch=1)

    splitter.addWidget(right_widget)

    # Give both panels equal initial width; right panel gets more stretch.
    splitter.setStretchFactor(0, 1)
    splitter.setStretchFactor(1, 2)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _append_log(direction: str, text: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] {direction.upper():>3} {text.rstrip()}"
        description = _describe_rapi(text)
        row_index = rapi_table.rowCount()
        rapi_table.insertRow(row_index)
        rapi_table.setItem(row_index, 0, QTableWidgetItem(line))
        rapi_table.setItem(row_index, 1, QTableWidgetItem(description))
        if rapi_table.rowCount() > max_log_lines:
            rapi_table.removeRow(0)
        rapi_table.scrollToBottom()

    def _traffic_hook(direction: str, frame: str) -> None:
        _append_log(direction, frame)

    def _refresh_summary() -> None:
        model = engine.model
        lbl_state.setText(f"0x{model.evse_state:02X}")
        lbl_pilot.setText(f"0x{model.pilot_state:02X}")
        lbl_flags.setText(f"0x{model.flags:04X}")
        lbl_vflags.setText(f"0x{model.vflags:04X}")
        lbl_current.setText(str(model.current_capacity_amps))

    def _apply_state_change() -> None:
        _refresh_summary()
        _app = _app_state["app"]
        if _app is not None:
            try:
                _app.notify_state_if_changed()
            except Exception as exc:  # pragma: no cover - UI runtime fallback
                _append_log("err", f"state notify failed: {exc}")

    def _set_connected_label(connected: bool, detail: str = "") -> None:
        text = "Connected" if connected else "Disconnected"
        if detail:
            text = f"{text}: {detail}"
        conn_status.setText(text)
        colour = "#2d7a2d" if connected else "#7a2d2d"
        conn_status.setStyleSheet(f"font-style: italic; color: {colour};")

    def _on_connect() -> None:
        if _app_state["app"] is not None:
            return
        selected_port = port_input.text().strip()
        selected_baud = baud_input.value()
        if not selected_port:
            _append_log("err", "serial port is required (example: /dev/ttyUSB0)")
            _set_connected_label(False, "missing port")
            return
        try:
            t = UartTransport(selected_port, selected_baud)
            t.open()
            _app_state["transport"] = t
            _app_state["app"] = SimulatorApp(
                t,
                dispatcher,
                send_boot_notification=send_boot_notification,
                traffic_hook=_traffic_hook,
            )
            _app_state["app"].process_once()
            _set_connected_label(True, f"{selected_port} @ {selected_baud}")
        except Exception as exc:  # pragma: no cover - depends on host serial setup
            _append_log("err", f"connect failed: {exc}")
            _set_connected_label(False, "connect failed")
            if _app_state["transport"] is not None:
                _app_state["transport"].close()
            _app_state["transport"] = None
            _app_state["app"] = None

    def _on_disconnect() -> None:
        if _app_state["transport"] is not None:
            try:
                _app_state["transport"].close()
            except Exception as exc:  # pragma: no cover - UI runtime fallback
                _append_log("err", f"disconnect warning: {exc}")
        _app_state["transport"] = None
        _app_state["app"] = None
        _set_connected_label(False)

    def _on_vehicle_change(index: int) -> None:
        value = vehicle_combo.currentText()
        response = _VEHICLE_CHOICES.get(str(value), VehicleResponse.DISCONNECTED)
        engine.set_vehicle_response(response)
        _apply_state_change()

    def _on_set_current(value: int) -> None:
        engine.set_current_capacity(value)
        current_slider.setValue(engine.model.current_capacity_amps)
        current_value_label.setText(str(engine.model.current_capacity_amps))
        _apply_state_change()

    def _on_set_service(btn_id: int) -> None:
        if btn_id in (1, 2):
            engine.model.svc_level = btn_id
            engine.set_current_capacity(engine.model.current_capacity_amps)
            current_slider.setValue(engine.model.current_capacity_amps)
            current_value_label.setText(str(engine.model.current_capacity_amps))
            _apply_state_change()

    def _act_enable() -> None:
        engine.enable()
        _apply_state_change()

    def _act_disable() -> None:
        engine.disable()
        _apply_state_change()

    def _act_sleep() -> None:
        engine.sleep()
        _apply_state_change()

    def _act_fault_gfi() -> None:
        engine.inject_gfi_fault()
        _apply_state_change()

    def _act_fault_nognd() -> None:
        engine.inject_no_ground_fault()
        _apply_state_change()

    def _act_fault_stuck() -> None:
        engine.inject_stuck_relay_fault()
        _apply_state_change()

    def _act_fault_diode() -> None:
        engine.inject_diode_fault()
        _apply_state_change()

    def _act_clear_fault() -> None:
        engine.clear_fault()
        _apply_state_change()

    # ------------------------------------------------------------------
    # Wire up signals
    # ------------------------------------------------------------------
    connect_btn.clicked.connect(_on_connect)
    disconnect_btn.clicked.connect(_on_disconnect)
    vehicle_combo.currentIndexChanged.connect(_on_vehicle_change)
    svc_btn_group.idClicked.connect(_on_set_service)
    current_slider.valueChanged.connect(_on_set_current)
    enable_btn.clicked.connect(_act_enable)
    disable_btn.clicked.connect(_act_disable)
    sleep_btn.clicked.connect(_act_sleep)
    gfi_btn.clicked.connect(_act_fault_gfi)
    nognd_btn.clicked.connect(_act_fault_nognd)
    stuck_btn.clicked.connect(_act_fault_stuck)
    diode_btn.clicked.connect(_act_fault_diode)
    clear_btn.clicked.connect(_act_clear_fault)

    # ------------------------------------------------------------------
    # Polling timer – drives the RAPI receive loop and refreshes the LCD.
    # ------------------------------------------------------------------
    def _poll() -> None:
        _app = _app_state["app"]
        if _app is not None:
            try:
                _app.process_once()
            except Exception as exc:  # pragma: no cover - depends on host serial setup
                _append_log("err", f"runtime error: {exc}")
                _on_disconnect()

        display.update_from_evse_state(engine.model)
        colour = _COLOUR_MAP.get(display.color, _DEFAULT_COLOUR)
        lcd_line1.setText(display.line1)
        lcd_line2.setText(display.line2)
        # Tint the LCD frame background to reflect the backlight colour.
        lcd_frame.setStyleSheet(
            f"QFrame {{ background-color: {colour}; border-radius: 4px; }}"
        )
        window.setWindowTitle(
            f"OpenEVSE Interactive Simulator [color 0x{display.color:01X}]"
        )
        _refresh_summary()

    timer = QTimer()
    timer.timeout.connect(_poll)
    timer.start(50)  # ~20 Hz

    # ------------------------------------------------------------------
    # Initial state
    # ------------------------------------------------------------------
    _refresh_summary()
    window.show()

    if port:
        _on_connect()

    qt_app.exec()

    timer.stop()
    _on_disconnect()

