"""Button name enum and evdev code mappings for Nintendo Switch 2 Pro Controller."""

from __future__ import annotations

from enum import StrEnum


class ButtonName(StrEnum):
    """All supported controller buttons."""

    A = "A"
    B = "B"
    X = "X"
    Y = "Y"
    L = "L"
    R = "R"
    ZL = "ZL"
    ZR = "ZR"
    PLUS = "plus"
    MINUS = "minus"
    HOME = "home"
    CAPTURE = "capture"
    L3 = "L3"  # Left stick click
    R3 = "R3"  # Right stick click
    DPAD_UP = "dpad_up"
    DPAD_DOWN = "dpad_down"
    DPAD_LEFT = "dpad_left"
    DPAD_RIGHT = "dpad_right"


class AnalogAxis(StrEnum):
    """Analog stick axes."""

    LEFT_X = "left_x"
    LEFT_Y = "left_y"
    RIGHT_X = "right_x"
    RIGHT_Y = "right_y"


# evdev button code -> ButtonName
# These are the standard Linux input event codes for the Pro Controller
BUTTON_CODE_MAP: dict[int, ButtonName] = {
    304: ButtonName.B,
    305: ButtonName.A,
    306: ButtonName.Y,
    307: ButtonName.X,
    308: ButtonName.L,
    309: ButtonName.R,
    310: ButtonName.ZL,
    311: ButtonName.ZR,
    312: ButtonName.MINUS,
    313: ButtonName.PLUS,
    314: ButtonName.L3,
    315: ButtonName.R3,
    316: ButtonName.HOME,
    317: ButtonName.CAPTURE,
}

# evdev HAT (dpad) value -> ButtonName or None (center)
DPAD_X_MAP: dict[int, ButtonName | None] = {
    -1: ButtonName.DPAD_LEFT,
    0: None,
    1: ButtonName.DPAD_RIGHT,
}

DPAD_Y_MAP: dict[int, ButtonName | None] = {
    -1: ButtonName.DPAD_UP,
    0: None,
    1: ButtonName.DPAD_DOWN,
}

# evdev ABS code -> AnalogAxis
AXIS_CODE_MAP: dict[int, AnalogAxis] = {
    0: AnalogAxis.LEFT_X,
    1: AnalogAxis.LEFT_Y,
    2: AnalogAxis.RIGHT_X,
    5: AnalogAxis.RIGHT_Y,
}
