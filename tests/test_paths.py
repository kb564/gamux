import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from gamux.paths import (
    config_dir,
    default_config_path,
    is_wsl2,
    rumble_fifo,
    runtime_dir,
    wsl_gateway,
)


def test_wsl_gateway():
    # Clear cache since it's lru_cache
    wsl_gateway.cache_clear()

    with patch("subprocess.run") as mock_run:
        # 1. Success
        mock_run.return_value = MagicMock(
            stdout="default via 172.17.0.1 dev eth0 proto bird\n", returncode=0
        )
        assert wsl_gateway() == "172.17.0.1"

        # 2. Failure
        wsl_gateway.cache_clear()
        mock_run.side_effect = FileNotFoundError()
        assert wsl_gateway() is None


def test_is_wsl2():
    with patch("pathlib.Path.read_text") as mock_read:
        # 1. WSL2
        mock_read.return_value = "Linux version 5.15.133.1-microsoft-standard-WSL2"
        assert is_wsl2() is True

        # 2. Not WSL2
        mock_read.return_value = "Linux version 5.15.0-71-generic"
        assert is_wsl2() is False

        # 3. OSError
        mock_read.side_effect = OSError()
        assert is_wsl2() is False


def test_runtime_dir_xdg(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("XDG_RUNTIME_DIR", tmpdir)
        p = runtime_dir()
        assert str(p) == os.path.join(tmpdir, "gamux")
        assert p.exists()


def test_runtime_dir_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    p = runtime_dir()
    assert "gamux-" in p.name
    assert p.exists()


def test_rumble_fifo() -> None:
    p = rumble_fifo()
    assert p.name == "rumble.fifo"
    assert p.parent.name.startswith("gamux")


def test_config_dir_xdg(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("XDG_CONFIG_HOME", tmpdir)
        p = config_dir()
        assert str(p) == os.path.join(tmpdir, "gamux")
        assert p.exists()


def test_config_dir_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    # Mocking Path.home() is harder, so we just check if it ends with .config/gamux
    p = config_dir()
    assert str(p).endswith(".config/gamux")
    assert p.exists()


def test_default_config_path() -> None:
    p = default_config_path()
    assert p.name == "config.toml"
    assert p.parent.name == "gamux"
