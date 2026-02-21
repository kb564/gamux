"""Gamux v2 configuration - Pydantic v2 based."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ControllerConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    device_path: str = ""
    """Path to evdev device. Empty string = auto-detect."""
    grab: bool = False
    """Exclusively grab the device (prevents events leaking to other apps)."""
    stick_deadzone: Annotated[float, Field(ge=0.0, le=1.0)] = 0.1
    stick_neutral_x: int = 0
    stick_neutral_y: int = 0


class VoiceConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str = "small"
    language: str = "ja"
    compute_type: Literal["int8", "float16", "float32"] = "int8"
    beam_size: Annotated[int, Field(ge=1, le=20)] = 5
    vad_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = 0.5
    silence_duration_ms: Annotated[int, Field(ge=100, le=5000)] = 500
    device: str = "auto"
    """Audio input device name or 'auto'."""


class TmuxConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    command_timeout: Annotated[float, Field(gt=0.0, le=60.0)] = 5.0
    """Timeout in seconds for tmux commands."""


class BridgeConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    host: str = ""
    """Bridge service host. Empty = auto-detect via WSL2 gateway."""
    port: Annotated[int, Field(ge=1, le=65535)] = 8765
    reconnect_interval: Annotated[float, Field(ge=0.5, le=30.0)] = 3.0


class RumbleConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    patterns: dict[str, list[tuple[int, int]]] = Field(default_factory=dict)
    """Named rumble patterns: {name: [(strong_magnitude, duration_ms), ...]}"""


class AppConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    controller: ControllerConfig = Field(default_factory=ControllerConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    tmux: TmuxConfig = Field(default_factory=TmuxConfig)
    bridge: BridgeConfig = Field(default_factory=BridgeConfig)
    rumble: RumbleConfig = Field(default_factory=RumbleConfig)
    bindings: dict[str, str] = Field(default_factory=dict)
    """Button binding map: {'ZL_A': 'action_name', ...}"""

    @field_validator("bindings")
    @classmethod
    def bindings_not_empty_values(cls, v: dict[str, str]) -> dict[str, str]:
        for key, action in v.items():
            if not action.strip():
                raise ValueError(f"Binding '{key}' has an empty action name.")
        return v

    @classmethod
    def load(cls, path: Path | None = None) -> AppConfig:
        """Load config from TOML file. Uses defaults if file not found."""
        from gamux.paths import default_config_path

        config_path = path or default_config_path()
        if not config_path.exists():
            return cls()

        with config_path.open("rb") as f:
            data = tomllib.load(f)

        return cls.model_validate(data)

    @classmethod
    def load_with_override(
        cls,
        base: Path | None = None,
        override: Path | None = None,
    ) -> AppConfig:
        """Load base config, then merge override TOML on top."""
        from gamux.paths import default_config_path

        base_path = base or default_config_path()
        base_data: dict[str, object] = {}
        if base_path.exists():
            with base_path.open("rb") as f:
                base_data = tomllib.load(f)

        if override and override.exists():
            with override.open("rb") as f:
                override_data = tomllib.load(f)
            base_data = _deep_merge(base_data, override_data)

        return cls.model_validate(base_data)


def _deep_merge(base: dict[str, object], override: dict[str, object]) -> dict[str, object]:
    """Recursively merge override into base."""
    result: dict[str, object] = dict(base)
    for key, value in override.items():
        base_value = result.get(key)
        if isinstance(base_value, dict) and isinstance(value, dict):
            result[key] = _deep_merge(base_value, value)
        else:
            result[key] = value
    return result
