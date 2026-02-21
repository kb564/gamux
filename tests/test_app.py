"""Tests for the main App class."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gamux.app import App
from gamux.config import AppConfig
from gamux.controller.buttons import ButtonName
from gamux.controller.reader import ButtonEvent


@pytest.fixture
def mock_config():
    return AppConfig(bindings={"A": "builtin:none", "ZL_A": "builtin:none"})


@pytest.fixture
def app(mock_config):
    with patch("gamux.voice.recognizer.VoiceRecognizer.load_model", new_callable=AsyncMock):
        return App(mock_config)


@pytest.mark.asyncio
async def test_app_setup(app):
    with patch.object(app._status, "set", new_callable=AsyncMock) as mock_status_set:
        await app.setup()

        # Check status updates
        mock_status_set.assert_any_call("loading model...")
        mock_status_set.assert_any_call("ready")

        # Check callback registration
        assert app._recognizer._on_transcript == app._on_transcript


@pytest.mark.asyncio
async def test_app_on_button_normal(app):
    with (
        patch.object(app._registry, "dispatch_by_string", new_callable=AsyncMock) as mock_dispatch,
        patch("gamux.tmux.current_pane", new_callable=AsyncMock, return_value="%1"),
        patch("gamux.tmux.current_session", new_callable=AsyncMock, return_value="sess"),
    ):
        # Press A (not ZL)
        event = ButtonEvent(button=ButtonName.A, pressed=True)
        await app._on_button(event)

        # Should dispatch "builtin:none" (from bindings)
        mock_dispatch.assert_called_once()
        args, _ = mock_dispatch.call_args
        assert args[0] == "builtin:none"
        assert args[1].tmux_pane == "%1"


@pytest.mark.asyncio
async def test_app_on_button_ptt(app):
    with (
        patch.object(app._registry, "dispatch_by_string", new_callable=AsyncMock) as mock_dispatch,
        patch.object(app._status, "set", new_callable=AsyncMock) as mock_status,
    ):
        # Press ZL (PTT)
        event_zl_down = ButtonEvent(button=ButtonName.ZL, pressed=True)
        await app._on_button(event_zl_down)

        assert app._ptt_active is True
        mock_status.assert_called_with("listening...")

        # Press A while ZL is down
        event_a = ButtonEvent(button=ButtonName.A, pressed=True)
        await app._on_button(event_a)

        # Should look up "ZL_A"
        mock_dispatch.assert_called_once()
        args, _ = mock_dispatch.call_args
        assert args[0] == "builtin:none"

        # Release ZL
        event_zl_up = ButtonEvent(button=ButtonName.ZL, pressed=False)
        await app._on_button(event_zl_up)

        assert app._ptt_active is False
        mock_status.assert_called_with("ready")


@pytest.mark.asyncio
async def test_app_on_transcript(app):
    with (
        patch("gamux.tmux.send_keys", new_callable=AsyncMock) as mock_send,
        patch("gamux.tmux.current_pane", new_callable=AsyncMock, return_value="%1"),
        patch("gamux.tmux.current_session", new_callable=AsyncMock, return_value="sess"),
    ):
        await app._on_transcript("hello world")

        mock_send.assert_called_once_with("%1", "hello world")


@pytest.mark.asyncio
async def test_app_shutdown(app):
    with (
        patch.object(app._status, "set", new_callable=AsyncMock) as mock_set,
        patch.object(app._status, "clear", new_callable=AsyncMock) as mock_clear,
        patch.object(app._recognizer, "shutdown", new_callable=AsyncMock) as mock_rec_shutdown,
        patch.object(app._rumble, "stop", new_callable=AsyncMock) as mock_rumble_stop,
    ):
        await app.shutdown()
        mock_set.assert_called_with("shutting down...")
        mock_rec_shutdown.assert_called_once()
        mock_rumble_stop.assert_called_once()
        mock_clear.assert_called_once()


@pytest.mark.asyncio
async def test_app_on_button_misc(app):
    # Release button (not ZL) - should be no-op
    event = ButtonEvent(button=ButtonName.A, pressed=False)
    await app._on_button(event)

    # Missing binding
    event_b = ButtonEvent(button=ButtonName.B, pressed=True)
    with patch.object(app._registry, "dispatch_by_string", new_callable=AsyncMock) as mock_dispatch:
        await app._on_button(event_b)
        mock_dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_app_audio_loop(app):
    import numpy as np

    from gamux.voice.source import AudioSource

    class MockSource(AudioSource):
        async def start(self):
            pass

        async def stop(self):
            pass

        async def chunks(self):
            yield np.zeros(480, dtype=np.float32)

    source = MockSource()

    with (
        patch.object(app._vad, "process") as mock_vad,
        patch.object(app._recognizer, "transcribe", new_callable=AsyncMock) as mock_transcribe,
    ):
        # 1. PTT not active
        app._ptt_active = False
        await app._audio_loop(source)
        mock_vad.assert_not_called()

        # 2. PTT active, speech ended
        app._ptt_active = True
        mock_result = MagicMock()
        mock_result.speech_ended = True
        mock_result.audio_buffer = [np.zeros(480)]
        mock_vad.return_value = mock_result

        await app._audio_loop(source)
        mock_transcribe.assert_called_once()


@pytest.mark.asyncio
async def test_app_on_analog(app):
    from gamux.controller.buttons import AnalogAxis
    from gamux.controller.reader import AnalogEvent

    # Currently a no-op but test for coverage
    await app._on_analog(AnalogEvent(axis=AnalogAxis.LEFT_X, value=128, normalized=0.0))


@pytest.mark.asyncio
async def test_app_audio_loop_invalid_source(app):
    # Pass a non-AudioSource object
    await app._audio_loop(object())
    # Should just return


@pytest.mark.asyncio
async def test_app_controller_loop(app):
    from gamux.controller.reader import ButtonEvent

    mock_controller = MagicMock()
    app._controller = mock_controller

    # Mock events() to return an async iterator
    async def mock_events():
        yield ButtonEvent(button=ButtonName.A, pressed=True)

    mock_controller.events.return_value = mock_events()

    with patch.object(app, "_on_button", new_callable=AsyncMock) as mock_on_button:
        await app._controller_loop()
        mock_on_button.assert_called_once()


@pytest.mark.asyncio
async def test_app_run(app):
    # Default config has bridge.port=8765, so it chooses BridgeSource
    with (
        patch("gamux.voice.source.BridgeSource", spec=True) as mock_bridge_source,
        patch("gamux.app.ControllerReader", spec=True) as mock_reader,
        patch("asyncio.gather", new_callable=AsyncMock) as mock_gather,
    ):
        mock_bridge_source.return_value.__aenter__.return_value = mock_bridge_source.return_value
        mock_reader.return_value.__aenter__.return_value = mock_reader.return_value

        await app.run()
        mock_bridge_source.assert_called_once()
        mock_reader.assert_called_once()
        mock_gather.assert_called_once()

    # Now test LocalSource by making bridge.port falsy
    # So we'll just mock the 'if' condition by patching the app's config
    app._config = MagicMock()
    app._config.bridge.host = ""
    app._config.bridge.port = 0

    with (
        patch("gamux.voice.source.LocalSource", spec=True) as mock_local_source,
        patch("gamux.app.ControllerReader", spec=True) as mock_reader,
        patch("asyncio.gather", new_callable=AsyncMock) as mock_gather,
    ):
        mock_local_source.return_value.__aenter__.return_value = mock_local_source.return_value
        mock_reader.return_value.__aenter__.return_value = mock_reader.return_value

        await app.run()
        mock_local_source.assert_called_once()
