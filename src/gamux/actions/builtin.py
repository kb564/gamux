"""Built-in Gamux action handlers."""

from __future__ import annotations

from gamux.actions.context import ActionContext
from gamux.actions.names import ActionName
from gamux.actions.registry import ActionHandler


async def _switch_pane(ctx: ActionContext) -> None:
    await ctx.run_tmux("select-pane", "-t", ":.+")


async def _switch_pane_up(ctx: ActionContext) -> None:
    await ctx.run_tmux("select-pane", "-U")


async def _switch_pane_down(ctx: ActionContext) -> None:
    await ctx.run_tmux("select-pane", "-D")


async def _switch_pane_left(ctx: ActionContext) -> None:
    await ctx.run_tmux("select-pane", "-L")


async def _switch_pane_right(ctx: ActionContext) -> None:
    await ctx.run_tmux("select-pane", "-R")


async def _switch_window_next(ctx: ActionContext) -> None:
    await ctx.run_tmux("next-window")


async def _switch_window_prev(ctx: ActionContext) -> None:
    await ctx.run_tmux("previous-window")


async def _send_enter(ctx: ActionContext) -> None:
    await ctx.send_keys("Enter")


async def _send_escape(ctx: ActionContext) -> None:
    await ctx.send_keys("Escape")


async def _send_ctrl_c(ctx: ActionContext) -> None:
    await ctx.send_keys("C-c")


async def _confirm(ctx: ActionContext) -> None:
    await ctx.send_keys("Enter")


async def _cancel(ctx: ActionContext) -> None:
    await ctx.send_keys("Escape")


async def _scroll_up(ctx: ActionContext) -> None:
    await ctx.run_tmux("copy-mode")
    await ctx.run_tmux("send-keys", "-X", "scroll-up")


async def _scroll_down(ctx: ActionContext) -> None:
    await ctx.run_tmux("send-keys", "-X", "scroll-down")


async def _copy_mode(ctx: ActionContext) -> None:
    await ctx.run_tmux("copy-mode")


async def _paste(ctx: ActionContext) -> None:
    await ctx.run_tmux("paste-buffer")


async def _ptt_start(ctx: ActionContext) -> None:
    """Push-to-talk start — actual implementation in App layer."""
    del ctx


async def _ptt_stop(ctx: ActionContext) -> None:
    """Push-to-talk stop — actual implementation in App layer."""
    del ctx


BUILTIN_HANDLERS: dict[ActionName, ActionHandler] = {
    ActionName.SWITCH_PANE: _switch_pane,
    ActionName.SWITCH_PANE_UP: _switch_pane_up,
    ActionName.SWITCH_PANE_DOWN: _switch_pane_down,
    ActionName.SWITCH_PANE_LEFT: _switch_pane_left,
    ActionName.SWITCH_PANE_RIGHT: _switch_pane_right,
    ActionName.SWITCH_WINDOW_NEXT: _switch_window_next,
    ActionName.SWITCH_WINDOW_PREV: _switch_window_prev,
    ActionName.SEND_ENTER: _send_enter,
    ActionName.SEND_ESCAPE: _send_escape,
    ActionName.SEND_CTRL_C: _send_ctrl_c,
    ActionName.CONFIRM: _confirm,
    ActionName.CANCEL: _cancel,
    ActionName.SCROLL_UP: _scroll_up,
    ActionName.SCROLL_DOWN: _scroll_down,
    ActionName.COPY_MODE: _copy_mode,
    ActionName.PASTE: _paste,
    ActionName.PTT_START: _ptt_start,
    ActionName.PTT_STOP: _ptt_stop,
}
