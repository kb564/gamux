"""Tests for the Gamux CLI."""

from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from gamux.cli import app

runner = CliRunner()


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "game controller" in result.stdout


def test_cli_config_show(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text("[controller]\ndevice_path = '/dev/input/event0'")

    result = runner.invoke(app, ["config", "show", "--config", str(config_path)])
    assert result.exit_code == 0
    assert "controller" in result.stdout
    assert "/dev/input/event0" in result.stdout


def test_cli_config_validate_valid(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text("[voice]\nmodel = 'tiny'")

    result = runner.invoke(app, ["config", "validate", "--config", str(config_path)])
    assert result.exit_code == 0
    assert "Config valid" in result.stdout


def test_cli_config_validate_invalid(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text("[voice]\nvad_threshold = 'not-a-float'")

    result = runner.invoke(app, ["config", "validate", "--config", str(config_path)])
    assert result.exit_code == 1
    # Typer uses stderr for err=True
    assert "Config validation failed" in result.stderr


def test_cli_doctor_ok():
    with (
        patch("evdev.list_devices", return_value=["/dev/input/event0"]),
        patch("subprocess.run") as mock_run,
        patch("sounddevice.query_devices", return_value=[{"name": "mic"}]),
    ):
        mock_run.return_value.returncode = 0

        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "✓ evdev" in result.stdout
        assert "✓ tmux" in result.stdout
        assert "✓ sounddevice" in result.stdout


def test_cli_doctor_fail():
    with (
        patch("evdev.list_devices", return_value=[]),
        patch("subprocess.run") as mock_run,
        patch("sounddevice.query_devices", return_value=[]),
    ):
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = b"error"

        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 1
        assert "✗ evdev" in result.stdout
        assert "✗ tmux" in result.stdout
        assert "✗ sounddevice" in result.stdout


def test_cli_doctor_json():
    with (
        patch("evdev.list_devices", return_value=["/dev/input/event0"]),
        patch("subprocess.run") as mock_run,
        patch("sounddevice.query_devices", return_value=[{"name": "mic"}]),
    ):
        mock_run.return_value.returncode = 0

        result = runner.invoke(app, ["doctor", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert any(d["name"] == "evdev" and d["status"] == "ok" for d in data)
