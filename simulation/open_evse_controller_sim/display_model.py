"""Display simulation model (Step 9).

Maps EVSE state to 16x2 LCD text and RGB backlight colour following firmware
logic in firmware/open_evse/main.cpp:529-773, colour constants in
firmware/open_evse/open_evse.h:640-646, and display strings from
firmware/open_evse/Language_default.h (via strings.cpp / strings.h).

Colour integer values mirror the firmware #defines exactly:
    RED=0x1, GREEN=0x2, YELLOW=0x3, BLUE=0x4, VIOLET=0x5, TEAL=0x6, WHITE=0x7
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .evse_model import (
    ECVF_EV_CONNECTED,
    EVSE_STATE_A,
    EVSE_STATE_B,
    EVSE_STATE_C,
    EVSE_STATE_D,
    EVSE_STATE_DIODE_CHK_FAILED,
    EVSE_STATE_DISABLED,
    EVSE_STATE_GFCI_FAULT,
    EVSE_STATE_NO_GROUND,
    EVSE_STATE_SLEEPING,
    EVSE_STATE_STUCK_RELAY,
    EvseModel,
)

# ---------------------------------------------------------------------------
# Backlight colour constants (firmware/open_evse/open_evse.h:640-646)
# ---------------------------------------------------------------------------
LCD_RED    = 0x1  # #define RED    0x1
LCD_GREEN  = 0x2  # #define GREEN  0x2
LCD_YELLOW = 0x3  # #define YELLOW 0x3
LCD_BLUE   = 0x4  # #define BLUE   0x4
LCD_VIOLET = 0x5  # #define VIOLET 0x5
LCD_TEAL   = 0x6  # #define TEAL   0x6
LCD_WHITE  = 0x7  # #define WHITE  0x7

# ---------------------------------------------------------------------------
# Display string constants (Language_default.h via strings.cpp/strings.h)
# ---------------------------------------------------------------------------
STR_READY              = "Ready"             # g_psReady
STR_CONNECTED          = "Connected"         # g_psEvConnected
STR_CHARGING           = "Charging"          # g_psCharging
STR_DISABLED           = "Disabled"          # g_psDisabled
STR_SLEEPING           = "Sleeping"          # g_psSleeping
STR_EVSE_ERROR         = "EVSE ERROR"        # g_psEvseError
STR_SERVICE_REQUIRED   = "SERVICE REQUIRED"  # g_psSvcReq
STR_VENT_REQUIRED      = "VENT REQUIRED"     # g_psVentReq
STR_DIODE_CHECK_FAILED = "DIODE CHECK"       # g_psDiodeChkFailed
STR_GFCI_FAULT         = "GFCI FAULT"        # g_psGfciFault
STR_NO_GROUND          = "NO GROUND"         # g_psNoGround
STR_STUCK_RELAY        = "STUCK RELAY"        # g_psStuckRelay


@dataclass
class DisplayModel:
    """Simulated 16x2 LCD display with RGB backlight.

    ``line1`` / ``line2`` mirror the LcdPrint_P(g_ps*) / LcdMsg_P() calls in
    ``OnboardDisplay::Update()`` (firmware/open_evse/main.cpp:529-773).
    ``color`` is one of the LCD_* integer constants defined above.
    """

    line1: str = field(default=STR_READY)
    line2: str = field(default="")
    color: int = field(default=LCD_GREEN)

    def update_from_evse_state(self, model: EvseModel) -> None:
        """Update display fields from the current EvseModel state.

        Mirrors the ``switch (curstate)`` block in
        ``OnboardDisplay::Update()`` (firmware/open_evse/main.cpp:529-773)
        for all states covered by the MVP simulator.

        SLEEPING uses WHITE when the EV is connected (ECVF_EV_CONNECTED set),
        VIOLET otherwise – matching main.cpp:757.
        """
        s = model.evse_state
        if s == EVSE_STATE_A:
            self.color = LCD_GREEN
            self.line1 = STR_READY
            self.line2 = ""
        elif s == EVSE_STATE_B:
            self.color = LCD_YELLOW
            self.line1 = STR_CONNECTED
            self.line2 = ""
        elif s == EVSE_STATE_C:
            self.color = LCD_TEAL
            self.line1 = STR_CHARGING
            self.line2 = ""
        elif s == EVSE_STATE_D:
            self.color = LCD_RED
            self.line1 = STR_EVSE_ERROR
            self.line2 = STR_VENT_REQUIRED
        elif s == EVSE_STATE_DIODE_CHK_FAILED:
            self.color = LCD_RED
            self.line1 = STR_EVSE_ERROR
            self.line2 = STR_DIODE_CHECK_FAILED
        elif s == EVSE_STATE_GFCI_FAULT:
            self.color = LCD_RED
            self.line1 = STR_GFCI_FAULT
            self.line2 = ""
        elif s == EVSE_STATE_NO_GROUND:
            self.color = LCD_RED
            self.line1 = STR_NO_GROUND
            self.line2 = ""
        elif s == EVSE_STATE_STUCK_RELAY:
            self.color = LCD_RED
            self.line1 = STR_EVSE_ERROR
            self.line2 = STR_STUCK_RELAY
        elif s == EVSE_STATE_DISABLED:
            self.color = LCD_VIOLET
            self.line1 = STR_DISABLED
            self.line2 = ""
        elif s == EVSE_STATE_SLEEPING:
            ev_connected = bool(model.vflags & ECVF_EV_CONNECTED)
            self.color = LCD_WHITE if ev_connected else LCD_VIOLET
            self.line1 = STR_SLEEPING
            self.line2 = ""
        else:
            self.color = LCD_RED
            self.line1 = STR_EVSE_ERROR
            self.line2 = ""

