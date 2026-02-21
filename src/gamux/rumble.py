"""Rumble feedback manager."""

from __future__ import annotations

import asyncio
import logging
import struct
from pathlib import Path

from gamux.config import RumbleConfig
from gamux.paths import rumble_fifo

logger = logging.getLogger(__name__)

# Default patterns if not specified in config
DEFAULT_PATTERNS: dict[str, list[tuple[int, int]]] = {
    "short": [(0xFFFF, 100)],
    "long": [(0xFFFF, 300)],
    "double": [(0xFFFF, 80), (0, 80), (0xFFFF, 80)],
    "error": [(0x8000, 500)],
}


class RumbleManager:
    """Sends rumble commands via FIFO to the bridge service.

    Patterns are loaded from config (RumbleConfig.patterns).
    Falls back to DEFAULT_PATTERNS for missing entries.
    """

    def __init__(self, config: RumbleConfig) -> None:
        self._config = config
        self._fifo: Path = rumble_fifo()
        self._patterns: dict[str, list[tuple[int, int]]] = {
            **DEFAULT_PATTERNS,
            **config.patterns,
        }
        self._lock = asyncio.Lock()

    async def play(self, pattern_name: str) -> None:
        """Play a named rumble pattern."""
        if not self._config.enabled:
            return

        pattern = self._patterns.get(pattern_name)
        if pattern is None:
            logger.warning("Unknown rumble pattern: %r", pattern_name)
            return

        async with self._lock:
            for magnitude, duration_ms in pattern:
                await self._send(magnitude, duration_ms)
                if duration_ms > 0:
                    await asyncio.sleep(duration_ms / 1000)
            # stop rumble
            await self._send(0, 0)

    async def stop(self) -> None:
        """Stop any ongoing rumble."""
        await self._send(0, 0)

    async def _send(self, magnitude: int, duration_ms: int) -> None:
        """Write a rumble command to the FIFO."""
        if not self._fifo.exists():
            return

        payload = struct.pack(">HH", magnitude & 0xFFFF, duration_ms & 0xFFFF)

        def _write_payload() -> None:
            with self._fifo.open("wb") as fd:
                fd.write(payload)

        try:
            await asyncio.to_thread(_write_payload)
        except OSError as e:
            logger.debug("Rumble FIFO write failed: %s", e)
