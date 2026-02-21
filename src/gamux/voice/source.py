"""Audio source abstractions."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import suppress

import numpy as np

logger = logging.getLogger(__name__)

# Audio constants
SAMPLE_RATE = 16000
CHUNK_DURATION_MS = 30
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_DURATION_MS / 1000)  # 480


class AudioSource(ABC):
    """Abstract base class for audio input sources."""

    @abstractmethod
    async def start(self) -> None:
        """Open the audio source."""

    @abstractmethod
    async def stop(self) -> None:
        """Close the audio source."""

    @abstractmethod
    async def chunks(self) -> AsyncIterator[np.ndarray]:
        """Yield audio chunks as float32 numpy arrays at SAMPLE_RATE."""
        # mypy requires this: make it a generator
        yield np.zeros(CHUNK_SAMPLES, dtype=np.float32)  # pragma: no cover

    async def __aenter__(self) -> AudioSource:
        await self.start()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.stop()


class LocalSource(AudioSource):
    """Audio from local microphone via sounddevice."""

    def __init__(self, device: str | None = None, sample_rate: int = SAMPLE_RATE) -> None:
        self._device = device if device and device != "auto" else None
        self._sample_rate = sample_rate
        self._queue: asyncio.Queue[np.ndarray] = asyncio.Queue(maxsize=50)
        self._stream: object | None = None

    async def start(self) -> None:
        import sounddevice as sd

        loop = asyncio.get_running_loop()

        def _callback(
            indata: np.ndarray,
            frames: int,
            time: object,
            status: object,
        ) -> None:
            del frames, time
            if status:
                logger.warning("Audio status: %s", status)
            chunk = indata[:, 0].copy().astype(np.float32)
            with suppress(asyncio.QueueFull):
                loop.call_soon_threadsafe(self._queue.put_nowait, chunk)

        self._stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype="float32",
            blocksize=CHUNK_SAMPLES,
            device=self._device,
            callback=_callback,
        )
        self._stream.start()  # type: ignore[union-attr]
        logger.info("LocalSource started (device=%s)", self._device or "default")

    async def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()  # type: ignore[union-attr]
            self._stream.close()  # type: ignore[union-attr]
            self._stream = None
        await self._queue.put(np.zeros(0, dtype=np.float32))  # sentinel

    async def chunks(self) -> AsyncIterator[np.ndarray]:
        while True:
            chunk = await self._queue.get()
            if chunk.size == 0:
                break
            yield chunk


class BridgeSource(AudioSource):
    """Audio from Windows bridge service via WebSocket (WSL2 only)."""

    def __init__(self, host: str = "", port: int = 8765, sample_rate: int = SAMPLE_RATE) -> None:
        from gamux.paths import wsl_gateway

        self._host = host or wsl_gateway() or "127.0.0.1"
        self._port = port
        self._sample_rate = sample_rate
        self._queue: asyncio.Queue[np.ndarray] = asyncio.Queue(maxsize=50)
        self._ws: object | None = None
        self._task: asyncio.Task[None] | None = None

    @property
    def uri(self) -> str:
        return f"ws://{self._host}:{self._port}/audio"

    async def start(self) -> None:
        self._task = asyncio.create_task(self._receive_loop(), name="bridge-source")
        logger.info("BridgeSource connecting to %s", self.uri)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self._queue.put(np.zeros(0, dtype=np.float32))  # sentinel

    async def chunks(self) -> AsyncIterator[np.ndarray]:
        while True:
            chunk = await self._queue.get()
            if chunk.size == 0:
                break
            yield chunk

    async def _receive_loop(self) -> None:
        try:
            import websockets  # type: ignore[import-untyped]

            async with websockets.connect(self.uri) as ws:
                self._ws = ws
                logger.info("BridgeSource connected.")
                async for message in ws:
                    if isinstance(message, bytes):
                        pcm = np.frombuffer(message, dtype=np.int16).astype(np.float32) / 32768.0
                        with suppress(asyncio.QueueFull):
                            self._queue.put_nowait(pcm)
        except asyncio.CancelledError:
            pass
        except Exception as e:  # pragma: no cover - network/runtime dependent
            logger.error("BridgeSource error: %s", e)
        finally:
            await self._queue.put(np.zeros(0, dtype=np.float32))
