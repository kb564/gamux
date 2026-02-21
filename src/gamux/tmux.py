"""tmux command wrapper with timeout support."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 5.0


class TmuxError(Exception):
    """Raised when a tmux command fails."""


class TmuxTimeoutError(TmuxError):
    """Raised when a tmux command times out."""


async def run(
    *args: str,
    timeout: float = DEFAULT_TIMEOUT,
    check: bool = False,
) -> tuple[int, str, str]:
    """Run a tmux command.

    Returns (returncode, stdout, stderr).
    Raises TmuxTimeoutError if the command exceeds `timeout` seconds.
    Raises TmuxError if check=True and returncode != 0.
    """
    proc = await asyncio.create_subprocess_exec(
        "tmux",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError as exc:
        proc.kill()
        await proc.communicate()
        raise TmuxTimeoutError(f"tmux {args[0]!r} timed out after {timeout}s") from exc

    rc = proc.returncode or 0
    stdout = stdout_b.decode()
    stderr = stderr_b.decode()

    if check and rc != 0:
        raise TmuxError(f"tmux {args[0]!r} failed (rc={rc}): {stderr.strip()}")

    return rc, stdout, stderr


async def send_keys(target: str, keys: str, timeout: float = DEFAULT_TIMEOUT) -> None:
    """Send keys to a tmux pane."""
    await run("send-keys", "-t", target, keys, "", timeout=timeout, check=True)


async def current_pane(timeout: float = DEFAULT_TIMEOUT) -> str:
    """Return the current tmux pane ID."""
    _, stdout, _ = await run(
        "display-message",
        "-p",
        "#{pane_id}",
        timeout=timeout,
        check=True,
    )
    return stdout.strip()


async def current_session(timeout: float = DEFAULT_TIMEOUT) -> str:
    """Return the current tmux session name."""
    _, stdout, _ = await run(
        "display-message",
        "-p",
        "#{session_name}",
        timeout=timeout,
        check=True,
    )
    return stdout.strip()
