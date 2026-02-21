"""Tests for infrastructure components."""

from __future__ import annotations

import asyncio
import struct
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import gamux.tmux as tmux
from gamux.config import RumbleConfig
from gamux.rumble import RumbleManager
from gamux.status import StatusManager

# --- tmux tests ---


@pytest.mark.asyncio
async def test_tmux_run_success():
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"output\n", b"")
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        rc, stdout, stderr = await tmux.run("display-message", "-p", "hello")

        assert rc == 0
        assert stdout == "output\n"
        assert stderr == ""
        mock_exec.assert_called_once_with(
            "tmux",
            "display-message",
            "-p",
            "hello",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )


@pytest.mark.asyncio
async def test_tmux_run_error():
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"error msg\n")
        mock_proc.returncode = 1
        mock_exec.return_value = mock_proc

        with pytest.raises(tmux.TmuxError, match=r"failed \(rc=1\): error msg"):
            await tmux.run("invalid", check=True)


@pytest.mark.asyncio
async def test_tmux_run_timeout():
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock()
        mock_proc.communicate.side_effect = [TimeoutError(), (b"", b"")]
        mock_proc.kill = MagicMock()
        mock_exec.return_value = mock_proc

        with pytest.raises(tmux.TmuxTimeoutError, match="timed out after 0.1s"):
            await tmux.run("sleep", timeout=0.1)

        mock_proc.kill.assert_called_once()
        assert mock_proc.communicate.await_count == 2


@pytest.mark.asyncio
async def test_tmux_helpers():
    with patch("gamux.tmux.run") as mock_run:
        mock_run.return_value = (0, " %1 \n", "")
        pane = await tmux.current_pane()
        assert pane == "%1"
        mock_run.assert_called_with("display-message", "-p", "#{pane_id}", timeout=5.0, check=True)

        mock_run.return_value = (0, "my-session\n", "")
        session = await tmux.current_session()
        assert session == "my-session"
        mock_run.assert_called_with(
            "display-message", "-p", "#{session_name}", timeout=5.0, check=True
        )

        mock_run.return_value = (0, "", "")
        await tmux.send_keys("%1", "hello")
        mock_run.assert_called_with("send-keys", "-t", "%1", "hello", "", timeout=5.0, check=True)


# --- rumble tests ---


@pytest.mark.asyncio
async def test_rumble_manager_play():
    config = RumbleConfig(enabled=True, patterns={"test": [(0xFFFF, 50)]})

    with patch("gamux.rumble.rumble_fifo") as mock_fifo_path:
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_fifo_path.return_value = mock_path

        manager = RumbleManager(config)

        with patch.object(mock_path, "open") as mock_open:
            mock_file = MagicMock()
            mock_open.return_value.__enter__.return_value = mock_file

            await manager.play("test")

            # Should write pattern then 0,0 to stop
            expected_payload = struct.pack(">HH", 0xFFFF, 50)
            stop_payload = struct.pack(">HH", 0, 0)

            # Check calls to write
            calls = [c.args[0] for c in mock_file.write.call_args_list]
            assert expected_payload in calls
            assert stop_payload in calls


@pytest.mark.asyncio
async def test_rumble_manager_unknown_pattern():
    config = RumbleConfig(enabled=True)
    manager = RumbleManager(config)
    # Should just return without error
    await manager.play("non-existent")


@pytest.mark.asyncio
async def test_rumble_manager_stop():
    config = RumbleConfig(enabled=True)
    with patch("gamux.rumble.rumble_fifo") as mock_fifo_path:
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_fifo_path.return_value = mock_path
        manager = RumbleManager(config)

        with patch.object(mock_path, "open") as mock_open:
            mock_file = MagicMock()
            mock_open.return_value.__enter__.return_value = mock_file
            await manager.stop()

            stop_payload = struct.pack(">HH", 0, 0)
            mock_file.write.assert_called_with(stop_payload)


@pytest.mark.asyncio
async def test_rumble_manager_fifo_missing():
    config = RumbleConfig(enabled=True)
    with patch("gamux.rumble.rumble_fifo") as mock_fifo_path:
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = False
        mock_fifo_path.return_value = mock_path
        manager = RumbleManager(config)
        await manager.play("short")
        # Should return silently


@pytest.mark.asyncio
async def test_rumble_manager_oserror():
    config = RumbleConfig(enabled=True)
    with patch("gamux.rumble.rumble_fifo") as mock_fifo_path:
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.open.side_effect = OSError("Access denied")
        mock_fifo_path.return_value = mock_path

        manager = RumbleManager(config)
        await manager.play("short")
        # Should catch OSError and return silently


@pytest.mark.asyncio
async def test_rumble_manager_disabled():
    config = RumbleConfig(enabled=False)
    with patch("gamux.rumble.rumble_fifo") as mock_fifo_path:
        mock_path = MagicMock(spec=Path)
        mock_fifo_path.return_value = mock_path
        manager = RumbleManager(config)
        await manager.play("short")
        mock_path.exists.assert_not_called()


# --- status tests ---


@pytest.mark.asyncio
async def test_status_manager():
    with patch("gamux.tmux.run") as mock_run:
        manager = StatusManager(session="s", window="w")

        await manager.set("working")

        # Check tmux calls for setting status
        # 1. set-window-option -t s:w automatic-rename off
        # 2. rename-window -t s:w [Gamux] working
        mock_run.assert_any_call("set-window-option", "-t", "s:w", "automatic-rename", "off")
        mock_run.assert_any_call("rename-window", "-t", "s:w", "[Gamux] working")

        mock_run.reset_mock()
        # Set same message again
        await manager.set("working")
        mock_run.assert_not_called()

        mock_run.reset_mock()
        await manager.clear()
        # 1. set-window-option -t s:w automatic-rename on
        mock_run.assert_called_once_with("set-window-option", "-t", "s:w", "automatic-rename", "on")
