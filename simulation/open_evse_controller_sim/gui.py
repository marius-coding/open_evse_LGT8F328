"""DearPyGui interactive simulator window.

DearPyGui is imported lazily inside :func:`build_gui` so that the rest of the
simulator (including tests) can be imported without a display server or
DearPyGui installed.  Install it with ``pip install dearpygui`` before calling
``build_gui()``.

The window renders a 16x2 simulated LCD, interactive EV/operator controls,
optional live serial connectivity to an ESP target, and a RAPI RX/TX monitor.
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
from .evse_model import EvseStateEngine, VehicleResponse
from .rapi_dispatch import RapiDispatcher
from .simulator_app import SimulatorApp
from .transport_uart import SERIAL_BAUD, UartTransport

# Mapping from firmware LCD colour integers to DearPyGui [R, G, B, A] tuples.
# Hue choices follow standard J1772 / Adafruit RGB LCD conventions.
_COLOUR_MAP: dict[int, tuple[int, int, int, int]] = {
    LCD_RED:    (220,  50,  50, 255),
    LCD_GREEN:  ( 50, 200,  50, 255),
    LCD_YELLOW: (220, 200,  50, 255),
    LCD_BLUE:   ( 50,  50, 220, 255),
    LCD_VIOLET: (160,  50, 200, 255),
    LCD_TEAL:   ( 50, 200, 180, 255),
    LCD_WHITE:  (230, 230, 230, 255),
}
_DEFAULT_COLOUR: tuple[int, int, int, int] = (128, 128, 128, 255)

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
    """Build and run the DearPyGui simulator window.

    Creates a minimal display panel showing the 16x2 LCD simulation driven by
    *engine*.  If *engine* is ``None`` a default
    :class:`~open_evse_controller_sim.evse_model.EvseStateEngine` is used.

    The call blocks until the user closes the window.

    Raises:
        ImportError: propagated from ``import dearpygui.dearpygui`` when the
            package is not installed.  Install with ``pip install dearpygui``.
    """
    try:
        import dearpygui.dearpygui as dpg  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "dearpygui is required for build_gui(); install it with: pip install dearpygui"
        ) from exc

    if engine is None:
        engine = EvseStateEngine()

    display = DisplayModel()
    display.update_from_evse_state(engine.model)

    dispatcher = RapiDispatcher(engine.model)
    app: SimulatorApp | None = None
    transport: UartTransport | None = None
    rapi_rows: list[int] = []
    max_log_lines = 400

    def _append_log(direction: str, text: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] {direction.upper():>3} {text.rstrip()}"
        description = _describe_rapi(text)
        with dpg.table_row(parent="rapi_table") as row_id:
            dpg.add_text(line)
            dpg.add_text(description)
        rapi_rows.append(row_id)
        if len(rapi_rows) > max_log_lines:
            dpg.delete_item(rapi_rows.pop(0))
        dpg.set_y_scroll("rapi_table", dpg.get_y_scroll_max("rapi_table"))

    def _traffic_hook(direction: str, frame: str) -> None:
        _append_log(direction, frame)

    def _refresh_summary() -> None:
        model = engine.model
        dpg.set_value("state_value", f"0x{model.evse_state:02X}")
        dpg.set_value("pilot_value", f"0x{model.pilot_state:02X}")
        dpg.set_value("flags_value", f"0x{model.flags:04X}")
        dpg.set_value("vflags_value", f"0x{model.vflags:04X}")
        dpg.set_value("capacity_value", str(model.current_capacity_amps))

    def _apply_state_change() -> None:
        nonlocal app
        _refresh_summary()
        if app is not None:
            try:
                app.notify_state_if_changed()
            except Exception as exc:  # pragma: no cover - UI runtime fallback
                _append_log("err", f"state notify failed: {exc}")

    def _set_connected_label(connected: bool, detail: str = "") -> None:
        text = "Connected" if connected else "Disconnected"
        if detail:
            text = f"{text}: {detail}"
        dpg.set_value("conn_status", text)

    def _on_connect() -> None:
        nonlocal transport, app
        if app is not None:
            return
        selected_port = str(dpg.get_value("port_input") or "").strip()
        selected_baud = int(dpg.get_value("baud_input"))
        if not selected_port:
            _append_log("err", "serial port is required (example: /dev/ttyUSB0)")
            _set_connected_label(False, "missing port")
            return
        try:
            transport = UartTransport(selected_port, selected_baud)
            transport.open()
            app = SimulatorApp(
                transport,
                dispatcher,
                send_boot_notification=send_boot_notification,
                traffic_hook=_traffic_hook,
            )
            app.process_once()  # sends AB once (if enabled) and handles pending RX
            _set_connected_label(True, f"{selected_port} @ {selected_baud}")
        except Exception as exc:  # pragma: no cover - depends on host serial setup
            _append_log("err", f"connect failed: {exc}")
            _set_connected_label(False, "connect failed")
            if transport is not None:
                transport.close()
            transport = None
            app = None

    def _on_disconnect() -> None:
        nonlocal transport, app
        if transport is not None:
            try:
                transport.close()
            except Exception as exc:  # pragma: no cover - UI runtime fallback
                _append_log("err", f"disconnect warning: {exc}")
        transport = None
        app = None
        _set_connected_label(False)

    def _on_vehicle_change(_, value, __) -> None:
        response = _VEHICLE_CHOICES.get(str(value), VehicleResponse.DISCONNECTED)
        engine.set_vehicle_response(response)
        _apply_state_change()

    def _on_set_current(_, value, __) -> None:
        engine.set_current_capacity(int(value))
        dpg.set_value("current_slider", engine.model.current_capacity_amps)
        _apply_state_change()

    def _on_set_service(_, value, __) -> None:
        if str(value) in ("1", "2"):
            engine.model.svc_level = int(value)
            engine.set_current_capacity(engine.model.current_capacity_amps)
            dpg.set_value("current_slider", engine.model.current_capacity_amps)
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

    dpg.create_context()
    dpg.create_viewport(title="OpenEVSE Simulator", width=1080, height=760)
    dpg.setup_dearpygui()

    with dpg.window(
        label="OpenEVSE Interactive Simulator",
        tag="main_window",
        no_close=True,
        width=1060,
        height=740,
    ):
        with dpg.group(horizontal=True):
            with dpg.child_window(width=520, height=700, border=True):
                dpg.add_text("Connection")
                dpg.add_input_text(
                    tag="port_input",
                    label="Serial port",
                    default_value=port or "",
                    width=220,
                )
                dpg.add_input_int(
                    tag="baud_input",
                    label="Baud",
                    default_value=baudrate,
                    width=220,
                    min_value=1200,
                    max_value=3000000,
                    min_clamped=True,
                    max_clamped=True,
                )
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Connect", callback=lambda: _on_connect())
                    dpg.add_button(label="Disconnect", callback=lambda: _on_disconnect())
                dpg.add_text("Disconnected", tag="conn_status")

                dpg.add_separator()
                dpg.add_text("EV Controls")
                dpg.add_combo(
                    list(_VEHICLE_CHOICES.keys()),
                    default_value="Disconnected",
                    label="Vehicle",
                    callback=_on_vehicle_change,
                    width=220,
                )
                dpg.add_radio_button(
                    ["1", "2"],
                    label="Service level",
                    default_value=str(engine.model.svc_level),
                    callback=_on_set_service,
                    horizontal=True,
                )
                dpg.add_slider_int(
                    tag="current_slider",
                    label="Current (A)",
                    default_value=engine.model.current_capacity_amps,
                    min_value=6,
                    max_value=80,
                    callback=_on_set_current,
                    width=300,
                )
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Enable", callback=lambda: _act_enable())
                    dpg.add_button(label="Disable", callback=lambda: _act_disable())
                    dpg.add_button(label="Sleep", callback=lambda: _act_sleep())

                dpg.add_separator()
                dpg.add_text("Fault Injection")
                with dpg.group(horizontal=True):
                    dpg.add_button(label="GFI", callback=lambda: _act_fault_gfi())
                    dpg.add_button(label="No Ground", callback=lambda: _act_fault_nognd())
                    dpg.add_button(label="Stuck Relay", callback=lambda: _act_fault_stuck())
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Diode Fault", callback=lambda: _act_fault_diode())
                    dpg.add_button(label="Clear Fault", callback=lambda: _act_clear_fault())

                dpg.add_separator()
                dpg.add_text("State Snapshot")
                dpg.add_text("", tag="state_value", label="EVSE state")
                dpg.add_text("", tag="pilot_value", label="Pilot")
                dpg.add_text("", tag="capacity_value", label="Current")
                dpg.add_text("", tag="flags_value", label="Flags")
                dpg.add_text("", tag="vflags_value", label="VFlags")

            with dpg.child_window(width=520, height=700, border=True):
                dpg.add_text("LCD Display")
                with dpg.group(tag="lcd_bg"):
                    dpg.add_text(display.line1, tag="lcd_line1")
                    dpg.add_text(display.line2, tag="lcd_line2")

                dpg.add_separator()
                dpg.add_text("RAPI Traffic")
                with dpg.table(
                    tag="rapi_table",
                    header_row=True,
                    scrollY=True,
                    height=565,
                    borders_innerH=True,
                    borders_outerH=True,
                    borders_innerV=True,
                    borders_outerV=True,
                    policy=dpg.mvTable_SizingStretchProp,
                ):
                    dpg.add_table_column(label="Frame", init_width_or_weight=0.65)
                    dpg.add_table_column(label="Description", init_width_or_weight=0.35)

    dpg.set_primary_window("main_window", True)
    dpg.show_viewport()
    _refresh_summary()

    if port:
        _on_connect()

    while dpg.is_dearpygui_running():
        if app is not None:
            try:
                app.process_once()
            except Exception as exc:  # pragma: no cover - depends on host serial setup
                _append_log("err", f"runtime error: {exc}")
                _on_disconnect()

        display.update_from_evse_state(engine.model)
        colour = _COLOUR_MAP.get(display.color, _DEFAULT_COLOUR)
        dpg.set_value("lcd_line1", display.line1)
        dpg.set_value("lcd_line2", display.line2)
        dpg.configure_item("main_window", label=f"OpenEVSE Interactive Simulator [{display.color}]")
        _refresh_summary()
        # Tint the window background to reflect the backlight colour.
        with dpg.theme() as t:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(
                    dpg.mvThemeCol_WindowBg, colour, category=dpg.mvThemeCat_Core
                )
        dpg.bind_item_theme("main_window", t)
        dpg.render_dearpygui_frame()

    _on_disconnect()
    dpg.destroy_context()

