import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from bridge.service import BridgeConfig, BridgeServer


def test_bridge_config_defaults() -> None:
    config = BridgeConfig()
    assert config.host == "0.0.0.0"
    assert config.port == 8765
    assert config.sample_rate == 16000
    assert config.channels == 1
    assert config.chunk_ms == 30
    assert config.device == ""
    assert config.reconnect_interval == 3.0
    assert config.log_level == "INFO"


def test_bridge_config_load(tmp_path: Path) -> None:
    p = tmp_path / "bridge_test.toml"
    p.write_text("""
[server]
host = "127.0.0.1"
port = 9000

[audio]
sample_rate = 44100
channels = 2
chunk_ms = 20
device = "Microphone"

[service]
reconnect_interval = 5.0
log_level = "DEBUG"
""")
    config = BridgeConfig.load(p)
    assert config.host == "127.0.0.1"
    assert config.port == 9000
    assert config.sample_rate == 44100
    assert config.channels == 2
    assert config.chunk_ms == 20
    assert config.device == "Microphone"
    assert config.reconnect_interval == 5.0
    assert config.log_level == "DEBUG"


def test_bridge_config_chunk_frames() -> None:
    config = BridgeConfig(sample_rate=16000, chunk_ms=30)
    assert config.chunk_frames == 480


def test_bridge_server_init() -> None:
    config = BridgeConfig()
    server = BridgeServer(config)
    assert server._config == config
    assert server._running is False


@pytest.mark.asyncio
async def test_bridge_handle_client():
    config = BridgeConfig()
    server = BridgeServer(config)

    mock_ws = AsyncMock()
    mock_ws.remote_address = ("127.0.0.1", 12345)

    # Make wait_closed block until we say so
    stop_wait = asyncio.Event()
    mock_ws.wait_closed.side_effect = stop_wait.wait

    # Start task
    task = asyncio.create_task(server._handle_client(mock_ws))

    # Wait a bit to ensure it's added
    await asyncio.sleep(0.05)
    assert mock_ws in server._clients

    # Unblock and wait for task to finish
    stop_wait.set()
    await task

    assert mock_ws not in server._clients


@pytest.mark.asyncio
async def test_bridge_broadcast_loop():
    config = BridgeConfig()
    server = BridgeServer(config)
    server._running = True

    mock_ws = AsyncMock()
    server._clients.add(mock_ws)

    # Put chunk in queue
    await server._audio_queue.put(b"audio data")

    # Run loop for one iteration
    broadcast_task = asyncio.create_task(server._broadcast_loop())

    await asyncio.sleep(0.05)
    mock_ws.send.assert_called_with(b"audio data")

    # Stop loop
    server._running = False
    await server._audio_queue.put(b"stop")  # to unblock get()
    broadcast_task.cancel()
