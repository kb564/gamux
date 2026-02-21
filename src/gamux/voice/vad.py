"""Voice Activity Detection (VAD) - standalone module."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto

import numpy as np

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000


class VADState(Enum):
    SILENCE = auto()
    SPEECH = auto()
    TRAILING = auto()


@dataclass
class VADConfig:
    threshold: float = 0.5
    """RMS energy threshold for speech detection."""

    silence_duration_ms: int = 500
    """How long silence must persist before ending speech (ms)."""

    min_speech_ms: int = 100
    """Minimum speech duration to emit (ms)."""

    sample_rate: int = SAMPLE_RATE


@dataclass
class VADResult:
    """Result of processing one audio chunk."""

    speech_started: bool = False
    speech_ended: bool = False
    audio_buffer: list[np.ndarray] = field(default_factory=list)
    """Accumulated audio since speech started (only populated when speech_ended=True)."""


class VoiceActivityDetector:
    """Simple energy-based VAD.

    Usage::

        vad = VoiceActivityDetector(VADConfig(threshold=0.02))
        for chunk in audio_chunks:
            result = vad.process(chunk)
            if result.speech_ended:
                audio = np.concatenate(result.audio_buffer)
                # send audio to recognizer
    """

    def __init__(self, config: VADConfig | None = None) -> None:
        self._cfg = config or VADConfig()
        self._state = VADState.SILENCE
        self._buffer: list[np.ndarray] = []
        self._silence_samples = 0
        self._speech_samples = 0

        silence_chunks = int(self._cfg.silence_duration_ms / 1000 * self._cfg.sample_rate / 480)
        self._silence_threshold_chunks = max(1, silence_chunks)

    def reset(self) -> None:
        """Reset detector state."""
        self._state = VADState.SILENCE
        self._buffer.clear()
        self._silence_samples = 0
        self._speech_samples = 0

    def process(self, chunk: np.ndarray) -> VADResult:
        """Process one audio chunk. Returns VADResult."""
        result = VADResult()
        rms = float(np.sqrt(np.mean(chunk**2)))
        is_speech = rms >= self._cfg.threshold

        if self._state == VADState.SILENCE:
            if is_speech:
                self._state = VADState.SPEECH
                self._buffer = [chunk]
                self._speech_samples = len(chunk)
                self._silence_samples = 0
                result.speech_started = True

        elif self._state == VADState.SPEECH:
            self._buffer.append(chunk)
            if is_speech:
                self._speech_samples += len(chunk)
                self._silence_samples = 0
            else:
                self._silence_samples += 1
                if self._silence_samples >= self._silence_threshold_chunks:
                    min_samples = int(self._cfg.min_speech_ms / 1000 * self._cfg.sample_rate)
                    if self._speech_samples >= min_samples:
                        result.speech_ended = True
                        result.audio_buffer = list(self._buffer)
                    self.reset()

        return result
