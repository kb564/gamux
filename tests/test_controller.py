import asyncio
from unittest.mock import MagicMock, patch

import evdev
import pytest

from gamux.config import ControllerConfig
from gamux.controller.buttons import AnalogAxis, ButtonName
from gamux.controller.reader import AnalogEvent, ButtonEvent, ControllerReader


def test_button_name_enum():
    assert ButtonName.A == "A"
    assert ButtonName.ZL == "ZL"
    assert ButtonName.DPAD_UP == "dpad_up"


def test_normalization():
    # Test with default neutral (0)
    config = ControllerConfig(stick_deadzone=0.1, stick_neutral_x=0, stick_neutral_y=0)
    reader = ControllerReader(config)

    # Neutral
    assert reader._normalize(0, AnalogAxis.LEFT_X) == 0.0

    # Inside deadzone (0.1 * 32767 = 3276.7)
    assert reader._normalize(1000, AnalogAxis.LEFT_X) == 0.0
    assert reader._normalize(-1000, AnalogAxis.LEFT_X) == 0.0

    # Just outside deadzone
    # normalized = 4000 / 32767 = 0.12207...
    # scaled = (0.12207 - 0.1) / 0.9 = 0.0245...
    norm = reader._normalize(4000, AnalogAxis.LEFT_X)
    assert 0.0 < norm < 0.1

    # Max positive
    assert reader._normalize(32767, AnalogAxis.LEFT_X) == 1.0
    assert reader._normalize(40000, AnalogAxis.LEFT_X) == 1.0  # Clamped

    # Max negative
    assert reader._normalize(-32767, AnalogAxis.LEFT_X) == -1.0
    assert reader._normalize(-40000, AnalogAxis.LEFT_X) == -1.0  # Clamped


@pytest.mark.asyncio
async def test_controller_reader_events():
    config = ControllerConfig(device_path="/dev/input/event0")

    mock_device = MagicMock()
    mock_device.name = "Mock Controller"

    # Simulate evdev events
    class MockEv:
        def __init__(self, type, code, value):
            self.type = type
            self.code = code
            self.value = value

    async def mock_async_read_loop():
        # EV_KEY: BTN_SOUTH (304) -> ButtonName.B
        yield MockEv(evdev.ecodes.EV_KEY, 304, 1)  # Press B
        yield MockEv(evdev.ecodes.EV_KEY, 304, 0)  # Release B

        # EV_ABS: ABS_X (0) -> AnalogAxis.LEFT_X
        yield MockEv(evdev.ecodes.EV_ABS, 0, 32767)  # Move stick to max

        # EV_ABS: ABS_HAT0X (16) -> D-pad Left/Right
        yield MockEv(evdev.ecodes.EV_ABS, evdev.ecodes.ABS_HAT0X, -1)  # D-pad Left press
        yield MockEv(evdev.ecodes.EV_ABS, evdev.ecodes.ABS_HAT0X, 0)  # D-pad Left release (center)

        # Give some time for events to be processed before loop ends if needed,
        # but here we just end the loop.
        await asyncio.sleep(0.01)

    mock_device.async_read_loop.return_value = mock_async_read_loop()

    with patch("evdev.InputDevice", return_value=mock_device):
        reader = ControllerReader(config)
        await reader.start()

        events = []
        # We expect 5 events
        async for event in reader.events():
            events.append(event)
            if len(events) == 5:
                break

        await reader.stop()

    assert len(events) == 5
    assert events[0] == ButtonEvent(ButtonName.B, True)
    assert events[1] == ButtonEvent(ButtonName.B, False)

    assert isinstance(events[2], AnalogEvent)
    assert events[2].axis == AnalogAxis.LEFT_X
    assert events[2].normalized == 1.0

    assert events[3] == ButtonEvent(ButtonName.DPAD_LEFT, True)
    assert events[4] == ButtonEvent(ButtonName.DPAD_LEFT, False)


@pytest.mark.asyncio
async def test_find_device():
    with (
        patch("evdev.list_devices", return_value=["/dev/input/event0"]),
        patch("evdev.InputDevice") as mock_input_device,
    ):
        mock_dev = MagicMock()
        # BTN_SOUTH = 304
        mock_dev.capabilities.return_value = {("EV_KEY", 1): [("BTN_SOUTH", 304)]}
        mock_input_device.return_value = mock_dev

        config = ControllerConfig(device_path="")
        reader = ControllerReader(config)

        device_path = reader._find_device()
        assert device_path == "/dev/input/event0"
