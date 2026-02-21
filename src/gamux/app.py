"""Gamux application - wires all subsystems together."""

from __future__ import annotations

import asyncio
import logging

import gamux.tmux as tmux
from gamux.actions.context import ActionContext
from gamux.actions.registry import ActionRegistry
from gamux.config import AppConfig
from gamux.controller.buttons import ButtonName
from gamux.controller.reader import AnalogEvent, ButtonEvent, ControllerReader
from gamux.rumble import RumbleManager
from gamux.status import StatusManager
from gamux.voice.recognizer import VoiceRecognizer
from gamux.voice.vad import VADConfig, VoiceActivityDetector

logger = logging.getLogger(__name__)


class App:
    """Main Gamux application."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._registry = ActionRegistry.with_builtins()
        self._rumble = RumbleManager(config.rumble)
        self._status = StatusManager()
        self._recognizer = VoiceRecognizer(config.voice)
        self._vad = VoiceActivityDetector(
            VADConfig(
                threshold=config.voice.vad_threshold,
                silence_duration_ms=config.voice.silence_duration_ms,
            )
        )
        self._controller: ControllerReader | None = None
        self._ptt_active = False
        self._ptt_audio: list[object] = []

    async def setup(self) -> None:
        """Initialize all subsystems."""
        await self._status.set("loading model...")
        self._recognizer.set_transcript_callback(self._on_transcript)
        await self._recognizer.load_model()
        await self._status.set("ready")
        logger.info("Gamux ready.")

    async def run(self) -> None:
        """Start the main event loop."""
        from gamux.voice.source import BridgeSource, LocalSource

        # Choose audio source
        if self._config.bridge.host or self._config.bridge.port:
            source = BridgeSource(
                host=self._config.bridge.host,
                port=self._config.bridge.port,
            )
        else:
            source = LocalSource(device=self._config.voice.device)

        self._controller = ControllerReader(self._config.controller)

        async with source, self._controller:
            await asyncio.gather(
                self._controller_loop(),
                self._audio_loop(source),
            )

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        await self._status.set("shutting down...")
        await self._recognizer.shutdown()
        await self._rumble.stop()
        await self._status.clear()
        logger.info("Gamux shut down.")

    # --- Controller ---

    async def _controller_loop(self) -> None:
        if self._controller is None:
            return
        async for event in self._controller.events():
            if isinstance(event, ButtonEvent):
                await self._on_button(event)
            elif isinstance(event, AnalogEvent):
                await self._on_analog(event)

    async def _on_button(self, event: ButtonEvent) -> None:
        if event.button == ButtonName.ZL:
            if event.pressed:
                self._ptt_active = True
                self._ptt_audio.clear()
                self._vad.reset()
                await self._status.set("listening...")
            else:
                self._ptt_active = False
                await self._status.set("ready")
            return

        if not event.pressed:
            return

        # Build binding key e.g. "ZL_A"
        binding_key = f"ZL_{event.button}" if self._ptt_active else str(event.button)
        action_str = self._config.bindings.get(binding_key)
        if action_str is None:
            return

        ctx = await self._make_context()
        await self._registry.dispatch_by_string(action_str, ctx)

    async def _on_analog(self, event: AnalogEvent) -> None:
        del event
        # Analog handling reserved for future use

    # --- Audio / Voice ---

    async def _audio_loop(self, source: object) -> None:
        import numpy as np

        from gamux.voice.source import AudioSource

        if not isinstance(source, AudioSource):
            return

        async for chunk in source.chunks():
            if not self._ptt_active:
                continue

            result = self._vad.process(chunk)
            if result.speech_ended and result.audio_buffer:
                audio = np.concatenate(result.audio_buffer)
                await self._recognizer.transcribe(audio)

    async def _on_transcript(self, text: str) -> None:
        logger.info("Transcript: %s", text)
        ctx = await self._make_context()
        ctx.extra["transcript"] = text
        # Send transcript as keys to current pane
        if ctx.tmux_pane:
            await tmux.send_keys(ctx.tmux_pane, text)

    # --- Helpers ---

    async def _make_context(self) -> ActionContext:
        try:
            pane = await tmux.current_pane()
            session = await tmux.current_session()
        except Exception:  # pragma: no cover - tmux availability is environment dependent
            pane = ""
            session = ""
        return ActionContext(config=self._config, tmux_pane=pane, tmux_session=session)
