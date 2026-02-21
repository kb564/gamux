"""Voice recognizer using faster-whisper."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from gamux.config import VoiceConfig

logger = logging.getLogger(__name__)

TranscriptCallback = Callable[[str], Awaitable[None]]


class VoiceRecognizer:
    """Transcribes audio using faster-whisper in a bounded thread pool.

    - Uses a fixed-size ThreadPoolExecutor (max_workers=1 by default)
      to avoid unbounded thread creation.
    - Properly awaits all pending tasks on shutdown.
    """

    def __init__(self, config: VoiceConfig, max_workers: int = 1) -> None:
        self._config = config
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="whisper")
        self._model: object | None = None
        self._pending_tasks: set[asyncio.Task[None]] = set()
        self._on_transcript: TranscriptCallback | None = None

    def set_transcript_callback(self, callback: TranscriptCallback) -> None:
        """Set the callback invoked when transcription completes."""
        self._on_transcript = callback

    async def load_model(self) -> None:
        """Load the Whisper model (runs in executor to avoid blocking event loop)."""
        logger.info("Loading Whisper model: %s (%s)", self._config.model, self._config.compute_type)
        loop = asyncio.get_running_loop()
        self._model = await loop.run_in_executor(self._executor, self._load_model_sync)
        logger.info("Whisper model loaded.")

    def _load_model_sync(self) -> object:
        from faster_whisper import WhisperModel

        return WhisperModel(
            self._config.model,
            compute_type=self._config.compute_type,
        )

    async def transcribe(self, audio: np.ndarray) -> None:
        """Submit audio for transcription. Non-blocking - result delivered via callback."""
        if self._model is None:
            logger.warning("Transcribe called before model is loaded.")
            return

        task = asyncio.create_task(self._transcribe_task(audio))
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)

    async def _transcribe_task(self, audio: np.ndarray) -> None:
        loop = asyncio.get_running_loop()
        try:
            text = await loop.run_in_executor(
                self._executor,
                self._transcribe_sync,
                audio,
            )
            if text and self._on_transcript is not None:
                await self._on_transcript(text)
        except Exception:
            logger.exception("Transcription error")

    def _transcribe_sync(self, audio: np.ndarray) -> str:
        segments, _ = self._model.transcribe(  # type: ignore[union-attr]
            audio,
            language=self._config.language,
            beam_size=self._config.beam_size,
            vad_filter=False,  # VAD handled externally
        )
        return " ".join(seg.text.strip() for seg in segments).strip()

    async def shutdown(self) -> None:
        """Await all pending transcription tasks, then shut down executor."""
        if self._pending_tasks:
            logger.info("Waiting for %d pending transcription(s)...", len(self._pending_tasks))
            await asyncio.gather(*list(self._pending_tasks), return_exceptions=True)
        self._pending_tasks.clear()
        self._executor.shutdown(wait=False)
        logger.info("VoiceRecognizer shut down.")
