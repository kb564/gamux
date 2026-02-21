"""Async controller event reader."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

import evdev

from gamux.config import ControllerConfig
from gamux.controller.buttons import (
    AXIS_CODE_MAP,
    BUTTON_CODE_MAP,
    DPAD_X_MAP,
    DPAD_Y_MAP,
    AnalogAxis,
    ButtonName,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ButtonEvent:
    """A button press or release event."""

    button: ButtonName
    pressed: bool  # True = pressed, False = released


@dataclass(frozen=True)
class AnalogEvent:
    """An analog stick movement event."""

    axis: AnalogAxis
    value: int
    """Raw evdev value."""
    normalized: float
    """Normalized value in [-1.0, 1.0] after deadzone application."""


# Union type for all controller events
ControllerEvent = ButtonEvent | AnalogEvent


class ControllerReader:
    """Reads events from a game controller via evdev.

    Usage::

        reader = ControllerReader(config)
        await reader.start()
        async for event in reader.events():
            ...
        await reader.stop()

    Or use as async context manager::

        async with ControllerReader(config) as reader:
            async for event in reader.events():
                ...
    """

    def __init__(self, config: ControllerConfig) -> None:
        self._config = config
        self._device: evdev.InputDevice[str] | None = None
        self._queue: asyncio.Queue[ControllerEvent | None] = asyncio.Queue()
        self._read_task: asyncio.Task[None] | None = None
        self._running = False
        self._dpad_x: ButtonName | None = None  # currently pressed dpad X
        self._dpad_y: ButtonName | None = None  # currently pressed dpad Y

    async def start(self) -> None:
        """Open the device and start reading events."""
        device_path = self._config.device_path or self._find_device()
        if not device_path:
            raise RuntimeError(
                "No controller device found. Check 'controller.device_path' in config."
            )

        self._device = evdev.InputDevice(device_path)
        logger.info("Opened controller: %s (%s)", self._device.name, device_path)

        if self._config.grab:
            self._device.grab()
            logger.info("Controller grabbed exclusively.")

        self._running = True
        self._read_task = asyncio.create_task(self._read_loop(), name="controller-reader")

    async def stop(self) -> None:
        """Stop reading and release the device."""
        self._running = False
        await self._queue.put(None)  # sentinel

        if self._read_task is not None:
            self._read_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._read_task
            self._read_task = None

        if self._device is not None:
            if self._config.grab:
                with contextlib.suppress(OSError):
                    self._device.ungrab()
            self._device.close()
            self._device = None
            logger.info("Controller released.")

    async def events(self) -> AsyncIterator[ControllerEvent]:
        """Async iterator yielding controller events."""
        while True:
            event = await self._queue.get()
            if event is None:
                break
            yield event

    async def __aenter__(self) -> ControllerReader:
        await self.start()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.stop()

    # --- Internal ---

    def _find_device(self) -> str | None:
        """Auto-detect the first gamepad/joystick device."""
        for path in evdev.list_devices():
            try:
                dev = evdev.InputDevice(path)
                caps = dev.capabilities(verbose=True)
                # Check for EV_KEY with BTN_SOUTH (typical gamepad indicator)
                key_caps = caps.get(("EV_KEY", 1), [])
                dev.close()
                if any("BTN_SOUTH" in str(k) or "BTN_A" in str(k) for k in key_caps):
                    return path
            except (PermissionError, OSError):
                continue
        return None

    def _normalize(self, value: int, axis: AnalogAxis) -> float:
        """Normalize raw axis value to [-1.0, 1.0] with deadzone."""
        neutral_x = self._config.stick_neutral_x
        neutral_y = self._config.stick_neutral_y
        neutral = neutral_y if axis in (AnalogAxis.LEFT_Y, AnalogAxis.RIGHT_Y) else neutral_x

        centered = value - neutral
        max_range = 32767.0
        normalized = centered / max_range
        normalized = max(-1.0, min(1.0, normalized))

        deadzone = self._config.stick_deadzone
        if abs(normalized) < deadzone:
            return 0.0
        # Scale so deadzone edge = 0.0 and max = 1.0
        sign = 1.0 if normalized > 0 else -1.0
        return sign * (abs(normalized) - deadzone) / (1.0 - deadzone)

    async def _read_loop(self) -> None:
        """Main event reading loop."""
        if self._device is None:
            return
        try:
            async for ev in self._device.async_read_loop():
                if not self._running:
                    break

                if ev.type == evdev.ecodes.EV_KEY:
                    await self._handle_key(ev)
                elif ev.type == evdev.ecodes.EV_ABS:
                    await self._handle_abs(ev)

        except (OSError, asyncio.CancelledError):
            pass
        finally:
            await self._queue.put(None)

    async def _handle_key(self, ev: evdev.InputEvent) -> None:
        button = BUTTON_CODE_MAP.get(ev.code)
        if button is None:
            return
        pressed = ev.value == 1
        await self._queue.put(ButtonEvent(button=button, pressed=pressed))

    async def _handle_abs(self, ev: evdev.InputEvent) -> None:
        # Analog axes
        axis = AXIS_CODE_MAP.get(ev.code)
        if axis is not None:
            normalized = self._normalize(ev.value, axis)
            await self._queue.put(AnalogEvent(axis=axis, value=ev.value, normalized=normalized))
            return

        # D-pad (HAT)
        if ev.code == evdev.ecodes.ABS_HAT0X:
            new_btn = DPAD_X_MAP.get(ev.value)
            if self._dpad_x is not None:
                await self._queue.put(ButtonEvent(button=self._dpad_x, pressed=False))
            self._dpad_x = new_btn
            if new_btn is not None:
                await self._queue.put(ButtonEvent(button=new_btn, pressed=True))

        elif ev.code == evdev.ecodes.ABS_HAT0Y:
            new_btn = DPAD_Y_MAP.get(ev.value)
            if self._dpad_y is not None:
                await self._queue.put(ButtonEvent(button=self._dpad_y, pressed=False))
            self._dpad_y = new_btn
            if new_btn is not None:
                await self._queue.put(ButtonEvent(button=new_btn, pressed=True))
