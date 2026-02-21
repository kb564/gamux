"""Status display manager."""

from __future__ import annotations

import logging

import gamux.tmux as tmux

logger = logging.getLogger(__name__)


class StatusManager:
    """Updates tmux window name to reflect Gamux state."""

    PREFIX = "[Gamux]"

    def __init__(self, session: str = "", window: str = "") -> None:
        self._session = session
        self._window = window
        self._current = ""

    async def set(self, message: str) -> None:
        """Set the status message."""
        full = f"{self.PREFIX} {message}"
        if full == self._current:
            return
        self._current = full
        await self._update(full)

    async def clear(self) -> None:
        """Clear the status message."""
        self._current = ""
        await self._update("")

    async def _update(self, text: str) -> None:
        try:
            target = self._window or ""
            if self._session and self._window:
                target = f"{self._session}:{self._window}"

            args = ["set-window-option"]
            if target:
                args += ["-t", target]
            args += ["automatic-rename", "off" if text else "on"]
            await tmux.run(*args)

            if text:
                rename_args = ["rename-window"]
                if target:
                    rename_args += ["-t", target]
                rename_args.append(text)
                await tmux.run(*rename_args)
        except Exception as e:  # pragma: no cover - tmux availability is environment dependent
            logger.debug("Status update failed: %s", e)
