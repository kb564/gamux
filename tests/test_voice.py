"""Tests for the voice subsystem."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from gamux.config import VoiceConfig
from gamux.voice.recognizer import VoiceRecognizer
from gamux.voice.source import BridgeSource, LocalSource
from gamux.voice.vad import VADConfig, VADState, VoiceActivityDetector


def test_vad_silence_to_speech() -> None:
    """Test VAD transitions from SILENCE to SPEECH."""
    config = VADConfig(threshold=0.1, min_speech_ms=0)
    vad = VoiceActivityDetector(config)

    # Silence chunk
    silence = np.zeros(480, dtype=np.float32)
    result = vad.process(silence)
    assert not result.speech_started
    assert vad._state == VADState.SILENCE

    # Speech chunk
    speech = np.ones(480, dtype=np.float32)
    result = vad.process(speech)
    assert result.speech_started
    assert vad._state == VADState.SPEECH
    assert len(vad._buffer) == 1


def test_vad_speech_to_silence() -> None:
    """Test VAD transitions from SPEECH to SILENCE and emits audio."""
    # Set silence_duration_ms to 60ms (2 chunks of 30ms)
    config = VADConfig(threshold=0.1, silence_duration_ms=60, min_speech_ms=10)
    vad = VoiceActivityDetector(config)

    speech = np.ones(480, dtype=np.float32)
    silence = np.zeros(480, dtype=np.float32)

    # Start speech
    vad.process(speech)

    # 1st silence chunk
    result = vad.process(silence)
    assert not result.speech_ended
    assert vad._state == VADState.SPEECH

    # 2nd silence chunk -> triggers end
    result = vad.process(silence)
    assert result.speech_ended
    assert len(result.audio_buffer) == 3  # speech + 2 silence
    assert vad._state == VADState.SILENCE


def test_vad_min_speech_duration() -> None:
    """Test VAD ignores speech shorter than min_speech_ms."""
    config = VADConfig(threshold=0.1, silence_duration_ms=30, min_speech_ms=100)
    vad = VoiceActivityDetector(config)

    speech = np.ones(480, dtype=np.float32)
    silence = np.zeros(480, dtype=np.float32)

    # 1 chunk of speech = 30ms < 100ms
    vad.process(speech)
    result = vad.process(silence)

    assert result.speech_ended is False
    assert vad._state == VADState.SILENCE


@pytest.mark.asyncio
async def test_recognizer_transcribe() -> None:
    """Test VoiceRecognizer calling faster-whisper."""
    config = VoiceConfig(model="tiny", compute_type="float32", language="en")
    recognizer = VoiceRecognizer(config)

    mock_model = MagicMock()
    mock_segment = MagicMock()
    mock_segment.text = " hello world "
    mock_model.transcribe.return_value = ([mock_segment], None)

    with patch("faster_whisper.WhisperModel", return_value=mock_model):
        await recognizer.load_model()

        callback = AsyncMock()
        recognizer.set_transcript_callback(callback)

        audio = np.zeros(16000, dtype=np.float32)
        await recognizer.transcribe(audio)
        await recognizer.shutdown()

        callback.assert_called_once_with("hello world")


@pytest.mark.asyncio
async def test_local_source() -> None:
    """Test LocalSource interaction with sounddevice."""
    with patch("sounddevice.InputStream") as mock_input_stream:
        source = LocalSource(device="test-device")

        await source.start()
        mock_input_stream.assert_called_once()
        args, kwargs = mock_input_stream.call_args
        callback = kwargs["callback"]

        # Simulate audio chunk
        chunk = np.random.rand(480, 1).astype(np.float32)
        callback(chunk, 480, None, None)

        # Get chunk from source
        async for received_chunk in source.chunks():
            assert np.array_equal(received_chunk, chunk[:, 0])
            await source.stop()

        mock_input_stream.return_value.start.assert_called_once()
        mock_input_stream.return_value.stop.assert_called_once()


@pytest.mark.asyncio
async def test_bridge_source() -> None:
    """Test BridgeSource interaction with websockets."""
    mock_ws = AsyncMock()
    # Simulate receiving binary message (PCM16)
    pcm16 = np.array([1000, -1000], dtype=np.int16)
    mock_ws.__aiter__.return_value = [pcm16.tobytes()]

    mock_websockets = MagicMock()
    mock_websockets.connect = MagicMock()
    mock_websockets.connect.return_value.__aenter__.return_value = mock_ws

    with patch.dict("sys.modules", {"websockets": mock_websockets}):
        source = BridgeSource(host="localhost", port=1234)

        async with source:
            # We need to wait a bit for the receive loop to start and put data in the queue
            # Or just consume chunks
            async for chunk in source.chunks():
                assert chunk.size == 2
                assert np.allclose(chunk, pcm16.astype(np.float32) / 32768.0)
                break
