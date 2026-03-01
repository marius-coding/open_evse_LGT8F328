"""PySide6 interactive simulator window.

PySide6 is imported lazily inside :func:`build_gui` so that the rest of the
simulator (including tests) can be imported without a display server or
PySide6 installed.  Install it with ``pip install PySide6`` before calling
``build_gui()``.

The window renders a 16x2 simulated LCD, interactive EV/operator controls,
optional live serial connectivity to an ESP target, a RAPI RX/TX monitor,
and a prominent pilot-signal state indicator.
State mutations are applied through
:class:`~open_evse_controller_sim.evse_model.EvseStateEngine` and reflected in
the display model.
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
from .evse_model import (
    PILOT_STATE_N12,
    PILOT_STATE_P12,
    PILOT_STATE_PWM,
    EvseStateEngine,
    VehicleResponse,
)
from .rapi_dispatch import RapiDispatcher
from .simulator_app import SimulatorApp
from .transport_uart import SERIAL_BAUD, UartTransport

# Mapping from firmware LCD colour integers to CSS rgb() strings.
# Hue choices follow standard J1772 / Adafruit RGB LCD conventions.
_COLOUR_MAP: dict[int, str] = {
    LCD_RED:    "rgb(200,  50,  50)",
    LCD_GREEN:  "rgb( 40, 180,  40)",
    LCD_YELLOW: "rgb(210, 180,  30)",
    LCD_BLUE:   "rgb( 50,  80, 210)",
    LCD_VIOLET: "rgb(150,  40, 190)",
    LCD_TEAL:   "rgb( 30, 180, 160)",
    LCD_WHITE:  "rgb(210, 210, 210)",
}
_DEFAULT_COLOUR = "rgb(100, 100, 100)"

# Pilot state → (label, background colour, text colour)
_PILOT_DISPLAY: dict[int, tuple[str, str, str]] = {
    PILOT_STATE_P12: ("+12 V  (P12 - not connected)", "rgb(50,180,50)",   "#fff"),
    PILOT_STATE_PWM: ("PWM    (charging allowed)",    "rgb(30,160,220)",  "#fff"),
    PILOT_STATE_N12: ("-12 V  (N12 - fault/diode)",  "rgb(210,50,50)",   "#fff"),
}
_PILOT_DEFAULT = ("unknown", "rgb(100,100,100)", "#fff")

_VEHICLE_CHOICES = {
    "Disconnected": VehicleResponse.DISCONNECTED,
    "Connected idle": VehicleResponse.CONNECTED_IDLE,
    "Charging": VehicleResponse.CHARGING,
}

_MAX_SERIAL_BAUD = 3_000_000   # upper clamp for the baud-rate spin box
_POLL_INTERVAL_MS = 50          # GUI refresh / serial poll interval (~20 fps)

# ── dark-theme stylesheet ────────────────────────────────────────────────────
_QSS = """
QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: "Segoe UI", "DejaVu Sans", sans-serif;
    font-size: 13px;
}
QGroupBox {
    border: 1px solid #45475a;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 6px;
    font-weight: bold;
    color: #89b4fa;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QPushButton {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #585b70;
    border-radius: 4px;
    padding: 4px 12px;
    min-width: 70px;
}
QPushButton:hover  { background-color: #45475a; }
QPushButton:pressed { background-color: #585b70; }
QPushButton#btn_connect   { background-color: #40a02b; color: #fff; border-color: #2d7d1f; }
QPushButton#btn_connect:hover  { background-color: #2d7d1f; }
QPushButton#btn_disconnect { background-color: #e64553; color: #fff; border-color: #a0283a; }
QPushButton#btn_disconnect:hover { background-color: #a0283a; }
QPushButton#btn_fault { background-color: #fe640b; color: #fff; border-color: #c04500; }
QPushButton#btn_fault:hover { background-color: #c04500; }
QPushButton#btn_clear { background-color: #1e66f5; color: #fff; border-color: #1450c0; }
QPushButton#btn_clear:hover { background-color: #1450c0; }
QLineEdit, QSpinBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #585b70;
    border-radius: 4px;
    padding: 3px 6px;
}
QComboBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #585b70;
    border-radius: 4px;
    padding: 3px 6px;
}
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView {
    background-color: #313244;
    color: #cdd6f4;
    selection-background-color: #45475a;
}
QSlider::groove:horizontal {
    height: 6px;
    background: #45475a;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #89b4fa;
    border: none;
    width: 14px;
    height: 14px;
    margin: -4px 0;
    border-radius: 7px;
}
QSlider::sub-page:horizontal { background: #89b4fa; border-radius: 3px; }
QTextEdit {
    background-color: #11111b;
    color: #a6e3a1;
    border: 1px solid #45475a;
    border-radius: 4px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
}
QLabel#lcd_panel {
    background-color: #003300;
    color: #00ff66;
    border: 2px solid #006600;
    border-radius: 6px;
    padding: 10px 16px;
    font-family: "Courier New", "DejaVu Sans Mono", monospace;
    font-size: 18px;
    font-weight: bold;
    letter-spacing: 2px;
    min-height: 56px;
}
QLabel#pilot_badge {
    border-radius: 5px;
    padding: 6px 14px;
    font-size: 13px;
    font-weight: bold;
}
QRadioButton { spacing: 6px; }
QRadioButton::indicator {
    width: 14px; height: 14px;
    border-radius: 7px;
    border: 1px solid #585b70;
    background: #313244;
}
QRadioButton::indicator:checked { background: #89b4fa; border-color: #89b4fa; }
"""


def build_gui(
    engine: EvseStateEngine | None = None,
    *,
    port: str | None = None,
    baudrate: int = SERIAL_BAUD,
    send_boot_notification: bool = True,
) -> None:
    """Build and run the PySide6 simulator window.

    Creates a display panel showing the 16x2 LCD simulation driven by
    *engine*, plus a prominent pilot-signal state indicator.  If *engine*
    is ``None`` a default
    :class:`~open_evse_controller_sim.evse_model.EvseStateEngine` is used.

    The call blocks until the user closes the window.

    Raises:
        ImportError: propagated from ``import PySide6`` when the package is
            not installed.  Install with ``pip install PySide6``.
    """
    try:
        from PySide6.QtCore import Qt, QTimer  # type: ignore[import]
        from PySide6.QtGui import QFont  # type: ignore[import]
        from PySide6.QtWidgets import (  # type: ignore[import]
            QApplication,
            QButtonGroup,
            QComboBox,
            QGroupBox,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QMainWindow,
            QPushButton,
            QRadioButton,
            QScrollBar,
            QSlider,
            QSpinBox,
            QSplitter,
            QTextEdit,
            QVBoxLayout,
            QWidget,
        )
    except ImportError as exc:
        raise ImportError(
            "PySide6 is required for build_gui(); install it with: pip install PySide6"
        ) from exc

    import sys

    if engine is None:
        engine = EvseStateEngine()

    display = DisplayModel()
    display.update_from_evse_state(engine.model)

    dispatcher = RapiDispatcher(engine.model)
    _app_ref: SimulatorApp | None = None
    _transport: UartTransport | None = None
    rapi_log: list[str] = []
    max_log_lines = 400

    # ── QApplication ────────────────────────────────────────────────────────
    qt_app = QApplication.instance() or QApplication(sys.argv)
    qt_app.setStyleSheet(_QSS)

    # ── Main window ─────────────────────────────────────────────────────────
    win = QMainWindow()
    win.setWindowTitle("OpenEVSE Simulator")
    win.resize(1160, 820)

    central = QWidget()
    win.setCentralWidget(central)
    root_layout = QHBoxLayout(central)
    root_layout.setContentsMargins(10, 10, 10, 10)
    root_layout.setSpacing(10)

    # ── Left column (controls) ───────────────────────────────────────────────
    left_col = QWidget()
    left_layout = QVBoxLayout(left_col)
    left_layout.setSpacing(8)
    left_layout.setContentsMargins(0, 0, 0, 0)

    # ── Connection group ─────────────────────────────────────────────────────
    grp_conn = QGroupBox("Connection")
    conn_layout = QVBoxLayout(grp_conn)

    row_port = QHBoxLayout()
    row_port.addWidget(QLabel("Serial port:"))
    port_edit = QLineEdit(port or "")
    port_edit.setPlaceholderText("/dev/ttyUSB0")
    row_port.addWidget(port_edit)
    conn_layout.addLayout(row_port)

    row_baud = QHBoxLayout()
    row_baud.addWidget(QLabel("Baud rate:"))
    baud_spin = QSpinBox()
    baud_spin.setRange(1200, _MAX_SERIAL_BAUD)
    baud_spin.setValue(baudrate)
    baud_spin.setGroupSeparatorShown(False)
    row_baud.addWidget(baud_spin)
    conn_layout.addLayout(row_baud)

    row_btns = QHBoxLayout()
    btn_connect = QPushButton("Connect")
    btn_connect.setObjectName("btn_connect")
    btn_disconnect = QPushButton("Disconnect")
    btn_disconnect.setObjectName("btn_disconnect")
    row_btns.addWidget(btn_connect)
    row_btns.addWidget(btn_disconnect)
    conn_layout.addLayout(row_btns)

    lbl_conn_status = QLabel("⬤  Disconnected")
    lbl_conn_status.setStyleSheet("color: #f38ba8;")
    conn_layout.addWidget(lbl_conn_status)
    left_layout.addWidget(grp_conn)

    # ── EV Controls group ────────────────────────────────────────────────────
    grp_ev = QGroupBox("EV Controls")
    ev_layout = QVBoxLayout(grp_ev)

    row_vehicle = QHBoxLayout()
    row_vehicle.addWidget(QLabel("Vehicle:"))
    combo_vehicle = QComboBox()
    combo_vehicle.addItems(list(_VEHICLE_CHOICES.keys()))
    row_vehicle.addWidget(combo_vehicle)
    ev_layout.addLayout(row_vehicle)

    row_svc = QHBoxLayout()
    row_svc.addWidget(QLabel("Service level:"))
    svc_group = QButtonGroup()
    rb_svc1 = QRadioButton("L1")
    rb_svc2 = QRadioButton("L2")
    svc_group.addButton(rb_svc1, 1)
    svc_group.addButton(rb_svc2, 2)
    (rb_svc1 if engine.model.svc_level == 1 else rb_svc2).setChecked(True)
    row_svc.addWidget(rb_svc1)
    row_svc.addWidget(rb_svc2)
    row_svc.addStretch()
    ev_layout.addLayout(row_svc)

    row_current = QHBoxLayout()
    row_current.addWidget(QLabel("Current (A):"))
    slider_current = QSlider(Qt.Horizontal)
    slider_current.setRange(6, 80)
    slider_current.setValue(engine.model.current_capacity_amps)
    lbl_current_val = QLabel(str(engine.model.current_capacity_amps))
    lbl_current_val.setFixedWidth(28)
    row_current.addWidget(slider_current)
    row_current.addWidget(lbl_current_val)
    ev_layout.addLayout(row_current)

    row_ev_btns = QHBoxLayout()
    btn_enable = QPushButton("Enable")
    btn_disable = QPushButton("Disable")
    btn_sleep = QPushButton("Sleep")
    row_ev_btns.addWidget(btn_enable)
    row_ev_btns.addWidget(btn_disable)
    row_ev_btns.addWidget(btn_sleep)
    ev_layout.addLayout(row_ev_btns)
    left_layout.addWidget(grp_ev)

    # ── Fault Injection group ────────────────────────────────────────────────
    grp_fault = QGroupBox("Fault Injection")
    fault_layout = QVBoxLayout(grp_fault)

    row_f1 = QHBoxLayout()
    btn_gfi = QPushButton("GFI")
    btn_gfi.setObjectName("btn_fault")
    btn_nognd = QPushButton("No Ground")
    btn_nognd.setObjectName("btn_fault")
    btn_stuck = QPushButton("Stuck Relay")
    btn_stuck.setObjectName("btn_fault")
    row_f1.addWidget(btn_gfi)
    row_f1.addWidget(btn_nognd)
    row_f1.addWidget(btn_stuck)
    fault_layout.addLayout(row_f1)

    row_f2 = QHBoxLayout()
    btn_diode = QPushButton("Diode Fault")
    btn_diode.setObjectName("btn_fault")
    btn_clear = QPushButton("Clear Fault")
    btn_clear.setObjectName("btn_clear")
    row_f2.addWidget(btn_diode)
    row_f2.addWidget(btn_clear)
    row_f2.addStretch()
    fault_layout.addLayout(row_f2)
    left_layout.addWidget(grp_fault)

    # ── State Snapshot group ─────────────────────────────────────────────────
    grp_state = QGroupBox("State Snapshot")
    state_layout = QVBoxLayout(grp_state)

    def _make_kv_row(key: str) -> tuple[QHBoxLayout, QLabel]:
        row = QHBoxLayout()
        row.addWidget(QLabel(f"{key}:"))
        val = QLabel("—")
        val.setStyleSheet("color: #f9e2af; font-family: monospace;")
        row.addWidget(val)
        row.addStretch()
        return row, val

    row_s, lbl_evse_state   = _make_kv_row("EVSE state")
    row_p, lbl_pilot_raw    = _make_kv_row("Pilot (raw)")
    row_c, lbl_capacity     = _make_kv_row("Current cap")
    row_f, lbl_flags        = _make_kv_row("Flags")
    row_vf, lbl_vflags      = _make_kv_row("VFlags")
    for r in (row_s, row_p, row_c, row_f, row_vf):
        state_layout.addLayout(r)

    # Pilot signal badge – prominent visual indicator
    lbl_pilot_badge = QLabel("Pilot signal: —")
    lbl_pilot_badge.setObjectName("pilot_badge")
    lbl_pilot_badge.setAlignment(Qt.AlignCenter)
    state_layout.addWidget(lbl_pilot_badge)

    left_layout.addWidget(grp_state)
    left_layout.addStretch()

    # ── Right column (LCD + RAPI log) ────────────────────────────────────────
    right_col = QWidget()
    right_layout = QVBoxLayout(right_col)
    right_layout.setSpacing(8)
    right_layout.setContentsMargins(0, 0, 0, 0)

    # ── LCD Display group ────────────────────────────────────────────────────
    grp_lcd = QGroupBox("LCD Display")
    lcd_layout = QVBoxLayout(grp_lcd)

    lbl_lcd = QLabel(f"{display.line1}\n{display.line2}")
    lbl_lcd.setObjectName("lcd_panel")
    lbl_lcd.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    lbl_lcd.setTextFormat(Qt.PlainText)
    lcd_layout.addWidget(lbl_lcd)
    right_layout.addWidget(grp_lcd)

    # ── RAPI Traffic group ────────────────────────────────────────────────────
    grp_rapi = QGroupBox("RAPI Traffic")
    rapi_layout = QVBoxLayout(grp_rapi)
    rapi_log_widget = QTextEdit()
    rapi_log_widget.setReadOnly(True)
    rapi_log_widget.setLineWrapMode(QTextEdit.NoWrap)
    rapi_layout.addWidget(rapi_log_widget)
    right_layout.addWidget(grp_rapi, stretch=1)

    root_layout.addWidget(left_col, stretch=0)
    root_layout.addWidget(right_col, stretch=1)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _append_log(direction: str, text: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] {direction.upper():>3} {text.rstrip()}"
        rapi_log.append(line)
        if len(rapi_log) > max_log_lines:
            del rapi_log[: len(rapi_log) - max_log_lines]
        rapi_log_widget.setPlainText("\n".join(rapi_log))
        sb = rapi_log_widget.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _traffic_hook(direction: str, frame: str) -> None:
        _append_log(direction, frame)

    def _refresh_summary() -> None:
        model = engine.model
        lbl_evse_state.setText(f"0x{model.evse_state:02X}")
        lbl_pilot_raw.setText(f"0x{model.pilot_state:02X}")
        lbl_flags.setText(f"0x{model.flags:04X}")
        lbl_vflags.setText(f"0x{model.vflags:04X}")
        lbl_capacity.setText(f"{model.current_capacity_amps} A")

        ptext, pbg, pfg = _PILOT_DISPLAY.get(model.pilot_state, _PILOT_DEFAULT)
        lbl_pilot_badge.setText(f"Pilot:  {ptext}")
        lbl_pilot_badge.setStyleSheet(
            f"background-color: {pbg}; color: {pfg};"
            " border-radius: 5px; padding: 6px 14px;"
            " font-size: 13px; font-weight: bold;"
        )

    def _apply_state_change() -> None:
        nonlocal _app_ref
        _refresh_summary()
        if _app_ref is not None:
            try:
                _app_ref.notify_state_if_changed()
            except Exception as exc:  # pragma: no cover - UI runtime fallback
                _append_log("err", f"state notify failed: {exc}")

    def _set_conn_label(connected: bool, detail: str = "") -> None:
        if connected:
            text = f"⬤  Connected: {detail}" if detail else "⬤  Connected"
            lbl_conn_status.setStyleSheet("color: #a6e3a1;")
        else:
            text = f"⬤  Disconnected: {detail}" if detail else "⬤  Disconnected"
            lbl_conn_status.setStyleSheet("color: #f38ba8;")
        lbl_conn_status.setText(text)

    def _on_connect() -> None:
        nonlocal _transport, _app_ref
        if _app_ref is not None:
            return
        selected_port = port_edit.text().strip()
        selected_baud = baud_spin.value()
        if not selected_port:
            _append_log("err", "serial port is required (example: /dev/ttyUSB0)")
            _set_conn_label(False, "missing port")
            return
        try:
            _transport = UartTransport(selected_port, selected_baud)
            _transport.open()
            _app_ref = SimulatorApp(
                _transport,
                dispatcher,
                send_boot_notification=send_boot_notification,
                traffic_hook=_traffic_hook,
            )
            _app_ref.process_once()
            _set_conn_label(True, f"{selected_port} @ {selected_baud}")
        except Exception as exc:  # pragma: no cover - depends on host serial setup
            _append_log("err", f"connect failed: {exc}")
            _set_conn_label(False, "connect failed")
            if _transport is not None:
                _transport.close()
            _transport = None
            _app_ref = None

    def _on_disconnect() -> None:
        nonlocal _transport, _app_ref
        if _transport is not None:
            try:
                _transport.close()
            except Exception as exc:  # pragma: no cover - UI runtime fallback
                _append_log("err", f"disconnect warning: {exc}")
        _transport = None
        _app_ref = None
        _set_conn_label(False)

    def _on_vehicle_change(text: str) -> None:
        response = _VEHICLE_CHOICES.get(text, VehicleResponse.DISCONNECTED)
        engine.set_vehicle_response(response)
        _apply_state_change()

    def _on_current_slider(value: int) -> None:
        engine.set_current_capacity(value)
        lbl_current_val.setText(str(engine.model.current_capacity_amps))
        slider_current.setValue(engine.model.current_capacity_amps)
        _apply_state_change()

    def _on_svc_toggled() -> None:
        btn_id = svc_group.checkedId()
        if btn_id in (1, 2):
            engine.model.svc_level = btn_id
            engine.set_current_capacity(engine.model.current_capacity_amps)
            slider_current.setValue(engine.model.current_capacity_amps)
            lbl_current_val.setText(str(engine.model.current_capacity_amps))
            _apply_state_change()

    # ── Wire up signals ──────────────────────────────────────────────────────
    btn_connect.clicked.connect(_on_connect)
    btn_disconnect.clicked.connect(_on_disconnect)
    combo_vehicle.currentTextChanged.connect(_on_vehicle_change)
    slider_current.valueChanged.connect(_on_current_slider)
    rb_svc1.toggled.connect(lambda _: _on_svc_toggled())
    rb_svc2.toggled.connect(lambda _: _on_svc_toggled())
    btn_enable.clicked.connect(lambda: (engine.enable(), _apply_state_change()))
    btn_disable.clicked.connect(lambda: (engine.disable(), _apply_state_change()))
    btn_sleep.clicked.connect(lambda: (engine.sleep(), _apply_state_change()))
    btn_gfi.clicked.connect(lambda: (engine.inject_gfi_fault(), _apply_state_change()))
    btn_nognd.clicked.connect(lambda: (engine.inject_no_ground_fault(), _apply_state_change()))
    btn_stuck.clicked.connect(lambda: (engine.inject_stuck_relay_fault(), _apply_state_change()))
    btn_diode.clicked.connect(lambda: (engine.inject_diode_fault(), _apply_state_change()))
    btn_clear.clicked.connect(lambda: (engine.clear_fault(), _apply_state_change()))

    # ── Poll timer ───────────────────────────────────────────────────────────
    def _poll() -> None:
        nonlocal _app_ref
        if _app_ref is not None:
            try:
                _app_ref.process_once()
            except Exception as exc:  # pragma: no cover - depends on host serial setup
                _append_log("err", f"runtime error: {exc}")
                _on_disconnect()

        display.update_from_evse_state(engine.model)
        colour = _COLOUR_MAP.get(display.color, _DEFAULT_COLOUR)
        lcd_text = display.line1
        if display.line2:
            lcd_text += f"\n{display.line2}"
        lbl_lcd.setText(lcd_text)
        lbl_lcd.setStyleSheet(
            f"background-color: {colour};"
            " color: #fff; border: 2px solid #006600; border-radius: 6px;"
            " padding: 10px 16px; font-family: 'Courier New', monospace;"
            " font-size: 18px; font-weight: bold; letter-spacing: 2px;"
            " min-height: 56px;"
        )
        win.setWindowTitle(f"OpenEVSE Simulator  [{display.line1.strip()}]")
        _refresh_summary()

    timer = QTimer()
    timer.setInterval(_POLL_INTERVAL_MS)  # ~20 fps
    timer.timeout.connect(_poll)
    timer.start()

    # ── Initial state ────────────────────────────────────────────────────────
    _refresh_summary()
    _poll()
    win.show()

    if port:
        _on_connect()

    qt_app.exec()
    _on_disconnect()

