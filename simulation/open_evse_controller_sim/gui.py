"""DearPyGui integration entry point (Step 9 – display simulation widget).

DearPyGui is imported lazily inside :func:`build_gui` so that the rest of the
simulator (including tests) can be imported without a display server or
DearPyGui installed.  Install it with ``pip install dearpygui`` before calling
``build_gui()``.

The widget renders a 16x2 simulated LCD whose text and backlight colour are
driven by an :class:`~open_evse_controller_sim.evse_model.EvseStateEngine`
via :class:`~open_evse_controller_sim.display_model.DisplayModel`.
"""

from __future__ import annotations

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
from .evse_model import EvseStateEngine

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


def build_gui(engine: EvseStateEngine | None = None) -> None:
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

    dpg.create_context()
    dpg.create_viewport(title="OpenEVSE Simulator", width=480, height=160)
    dpg.setup_dearpygui()

    with dpg.window(
        label="LCD Display",
        tag="lcd_window",
        no_close=True,
        width=460,
        height=140,
    ):
        with dpg.group(tag="lcd_bg"):
            dpg.add_text(display.line1, tag="lcd_line1")
            dpg.add_text(display.line2, tag="lcd_line2")

    dpg.set_primary_window("lcd_window", True)
    dpg.show_viewport()

    while dpg.is_dearpygui_running():
        display.update_from_evse_state(engine.model)
        colour = _COLOUR_MAP.get(display.color, _DEFAULT_COLOUR)
        dpg.set_value("lcd_line1", display.line1)
        dpg.set_value("lcd_line2", display.line2)
        dpg.configure_item("lcd_window", label=f"LCD [{display.color}]")
        # Tint the window background to reflect the backlight colour.
        with dpg.theme() as t:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(
                    dpg.mvThemeCol_WindowBg, colour, category=dpg.mvThemeCat_Core
                )
        dpg.bind_item_theme("lcd_window", t)
        dpg.render_dearpygui_frame()

    dpg.destroy_context()

