from pathlib import Path

import pytest
from pydantic import ValidationError

from gamux.config import AppConfig, _deep_merge


def test_app_config_defaults() -> None:
    config = AppConfig()
    assert config.controller.grab is False
    assert config.voice.language == "ja"
    assert config.voice.beam_size == 5
    assert config.tmux.command_timeout == 5.0
    assert config.bridge.port == 8765
    assert config.rumble.enabled is True
    assert config.bindings == {}


def test_app_config_load_nonexistent(tmp_path: Path) -> None:
    # Should use defaults if file does not exist
    config = AppConfig.load(tmp_path / "nonexistent.toml")
    assert config == AppConfig()


def test_app_config_load_valid(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text("""
[controller]
device_path = "/dev/input/event0"
grab = true

[voice]
language = "en"
beam_size = 10

[bindings]
"ZL_A" = "test_action"
""")
    config = AppConfig.load(p)
    assert config.controller.device_path == "/dev/input/event0"
    assert config.controller.grab is True
    assert config.voice.language == "en"
    assert config.voice.beam_size == 10
    assert config.bindings["ZL_A"] == "test_action"


def test_app_config_validation_error() -> None:
    with pytest.raises(ValidationError):
        # beam_size must be >= 1
        AppConfig(voice={"beam_size": 0})


def test_app_config_bindings_validation() -> None:
    with pytest.raises(ValidationError):
        # Action name cannot be empty
        AppConfig(bindings={"ZL_A": "  "})


def test_deep_merge() -> None:
    base = {"a": 1, "b": {"c": 2}}
    override = {"b": {"d": 3}, "e": 4}
    result = _deep_merge(base, override)
    assert result == {"a": 1, "b": {"c": 2, "d": 3}, "e": 4}


def test_app_config_load_with_override(tmp_path: Path) -> None:
    base_p = tmp_path / "base.toml"
    base_p.write_text("""
[controller]
device_path = "/dev/input/event0"
[bindings]
"ZL_A" = "action1"
""")
    override_p = tmp_path / "override.toml"
    override_p.write_text("""
[controller]
grab = true
[bindings]
"ZL_B" = "action2"
""")
    config = AppConfig.load_with_override(base_p, override_p)
    assert config.controller.device_path == "/dev/input/event0"
    assert config.controller.grab is True
    assert config.bindings == {"ZL_A": "action1", "ZL_B": "action2"}
