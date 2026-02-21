"""Action name enum — type-safe action identifiers."""

from __future__ import annotations

from enum import StrEnum


class ActionName(StrEnum):
    """All built-in Gamux actions."""

    # tmux navigation
    SWITCH_PANE = "switch_pane"
    SWITCH_PANE_UP = "switch_pane_up"
    SWITCH_PANE_DOWN = "switch_pane_down"
    SWITCH_PANE_LEFT = "switch_pane_left"
    SWITCH_PANE_RIGHT = "switch_pane_right"
    SWITCH_WINDOW_NEXT = "switch_window_next"
    SWITCH_WINDOW_PREV = "switch_window_prev"

    # key sending
    SEND_ENTER = "send_enter"
    SEND_ESCAPE = "send_escape"
    SEND_CTRL_C = "send_ctrl_c"

    # voice
    PTT_START = "ptt_start"
    PTT_STOP = "ptt_stop"

    # system
    CONFIRM = "confirm"
    CANCEL = "cancel"
    SCROLL_UP = "scroll_up"
    SCROLL_DOWN = "scroll_down"
    COPY_MODE = "copy_mode"
    PASTE = "paste"
