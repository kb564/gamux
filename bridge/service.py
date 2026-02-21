"""Gamux Bridge Service - streams microphone audio to WSL2 via WebSocket.

Run on Windows:
    python bridge/service.py [--config bridge/config.toml]

Clients (Gamux in WSL2) connect to ws://<host>:<port>/audio and receive
raw 16-bit PCM audio chunks.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

WebSocketSet = set[Any]


@dataclass
class BridgeConfig:
    host: str = "0.0.0.0"
    port: int = 8765
    sample_rate: int = 16000
    channels: int = 1
    chunk_ms: int = 30
    device: str = ""
    reconnect_interval: float = 3.0
    log_level: str = "INFO"

    @classmethod
    def load(cls, path: Path) -> BridgeConfig:
        with path.open("rb") as f:
            data = tomllib.load(f)
        return cls(
            host=data.get("server", {}).get("host", cls.host),
            port=data.get("server", {}).get("port", cls.port),
            sample_rate=data.get("audio", {}).get("sample_rate", cls.sample_rate),
            channels=data.get("audio", {}).get("channels", cls.channels),
            chunk_ms=data.get("audio", {}).get("chunk_ms", cls.chunk_ms),
            device=data.get("audio", {}).get("device", cls.device),
            reconnect_interval=data.get("service", {}).get(
                "reconnect_interval", cls.reconnect_interval
            ),
            log_level=data.get("service", {}).get("log_level", cls.log_level),
        )

    @property
    def chunk_frames(self) -> int:
        return int(self.sample_rate * self.chunk_ms / 1000)


class BridgeServer:
    """WebSocket server that streams microphone audio to connected clients."""

    def __init__(self, config: BridgeConfig) -> None:
        self._config = config
        self._clients: WebSocketSet = set()
        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)
        self._running = False

    async def run(self) -> None:
        """Start server and audio capture concurrently."""
        try:
            import websockets.server as ws_server
        except ImportError:
            logger.error("websockets not installed. Run: pip install websockets")
            sys.exit(1)

        self._running = True
        logger.info("Bridge server starting on %s:%d", self._config.host, self._config.port)

        async with ws_server.serve(self._handle_client, self._config.host, self._config.port):
            await asyncio.gather(
                self._capture_loop(),
                self._broadcast_loop(),
            )

    async def _handle_client(self, ws: Any) -> None:
        """Handle a single WebSocket client connection."""
        client_addr = ws.remote_address
        logger.info("Client connected: %s", client_addr)
        self._clients.add(ws)
        try:
            await ws.wait_closed()
        finally:
            self._clients.discard(ws)
            logger.info("Client disconnected: %s", client_addr)

    async def _broadcast_loop(self) -> None:
        """Broadcast audio chunks to all connected clients."""
        while self._running:
            chunk = await self._audio_queue.get()
            if not self._clients:
                continue
            dead: WebSocketSet = set()
            for ws in list(self._clients):
                try:
                    await ws.send(chunk)
                except Exception:
                    dead.add(ws)
            self._clients -= dead

    async def _capture_loop(self) -> None:
        """Capture microphone audio in executor and push to queue."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._capture_sync, loop)

    def _capture_sync(self, loop: asyncio.AbstractEventLoop) -> None:
        """Blocking audio capture (runs in thread)."""
        try:
            import sounddevice as sd
        except ImportError:
            logger.error("sounddevice not installed. Run: pip install sounddevice")
            return

        cfg = self._config
        device = cfg.device or None
        logger.info(
            "Audio capture: %dHz, %dch, %dms chunks, device=%s",
            cfg.sample_rate,
            cfg.channels,
            cfg.chunk_ms,
            device or "default",
        )

        def callback(indata: Any, frames: int, time: Any, status: Any) -> None:
            del frames, time
            if status:
                logger.warning("Audio status: %s", status)
            import numpy as np

            pcm = (indata[:, 0] * 32767).astype(np.int16)
            raw = pcm.tobytes()
            with contextlib.suppress(Exception):
                loop.call_soon_threadsafe(self._audio_queue.put_nowait, raw)

        with sd.InputStream(
            samplerate=cfg.sample_rate,
            channels=cfg.channels,
            dtype="float32",
            blocksize=cfg.chunk_frames,
            device=device,
            callback=callback,
        ):
            while self._running:
                import time as _time

                _time.sleep(0.1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Gamux Bridge Service")
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=Path(__file__).parent / "config.toml",
        help="Path to config TOML (default: bridge/config.toml)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    config = BridgeConfig.load(args.config) if args.config.exists() else BridgeConfig()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    server = BridgeServer(config)
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        logger.info("Bridge stopped.")


if __name__ == "__main__":
    main()
