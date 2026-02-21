"""ActionContext — runtime context passed to action handlers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gamux.config import AppConfig


@dataclass
class ActionContext:
    """Runtime context available to every action handler."""

    config: AppConfig
    """Full application config."""

    tmux_pane: str = ""
    """Current tmux pane ID (e.g. '%0')."""

    tmux_session: str = ""
    """Current tmux session name."""

    extra: dict[str, object] = field(default_factory=dict)
    """Arbitrary extra data (e.g. voice transcript)."""

    async def run_tmux(
        self,
        *args: str,
        timeout: float | None = None,
    ) -> tuple[int, str, str]:
        """Run a tmux command. Returns (returncode, stdout, stderr)."""
        effective_timeout = timeout if timeout is not None else self.config.tmux.command_timeout
        proc = await asyncio.create_subprocess_exec(
            "tmux",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=effective_timeout
            )
        except TimeoutError as exc:
            proc.kill()
            await proc.communicate()
            raise TimeoutError(f"tmux {args[0]!r} timed out after {effective_timeout}s") from exc
        return proc.returncode or 0, stdout_b.decode(), stderr_b.decode()

    async def send_keys(self, keys: str, target: str | None = None) -> None:
        """Send keys to a tmux pane."""
        target_pane = target or self.tmux_pane or ""
        args = ["send-keys"]
        if target_pane:
            args += ["-t", target_pane]
        args += [keys, ""]
        await self.run_tmux(*args)
