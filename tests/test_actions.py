"""Tests for the actions subsystem."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from gamux.actions import ActionContext, ActionName, ActionRegistry
from gamux.config import AppConfig


@pytest.fixture
def mock_config() -> AppConfig:
    """Create a mock AppConfig."""
    config = AsyncMock(spec=AppConfig)
    # Mock nested tmux config
    from gamux.config import TmuxConfig

    config.tmux = TmuxConfig(command_timeout=1.0)
    return config


@pytest.fixture
def action_ctx(mock_config: AppConfig) -> ActionContext:
    """Create an ActionContext with a mock config."""
    return ActionContext(config=mock_config, tmux_pane="%0", tmux_session="test")


@pytest.mark.asyncio
async def test_action_context_run_tmux(action_ctx: ActionContext) -> None:
    """Test ActionContext.run_tmux calls tmux correctly."""
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"stdout", b"stderr")
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        returncode, stdout, stderr = await action_ctx.run_tmux("list-panes")

        assert returncode == 0
        assert stdout == "stdout"
        assert stderr == "stderr"
        mock_exec.assert_called_once_with(
            "tmux",
            "list-panes",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )


@pytest.mark.asyncio
async def test_action_context_send_keys(action_ctx: ActionContext) -> None:
    """Test ActionContext.send_keys calls run_tmux with correct arguments."""
    with patch.object(ActionContext, "run_tmux", new_callable=AsyncMock) as mock_run_tmux:
        await action_ctx.send_keys("Enter")

        mock_run_tmux.assert_called_once_with("send-keys", "-t", "%0", "Enter", "")


@pytest.mark.asyncio
async def test_action_context_send_keys_custom_target(action_ctx: ActionContext) -> None:
    """Test ActionContext.send_keys with a custom target pane."""
    with patch.object(ActionContext, "run_tmux", new_callable=AsyncMock) as mock_run_tmux:
        await action_ctx.send_keys("Enter", target="%1")

        mock_run_tmux.assert_called_once_with("send-keys", "-t", "%1", "Enter", "")


def test_action_registry_register() -> None:
    """Test ActionRegistry.register and has."""
    registry = ActionRegistry()
    handler = AsyncMock()

    registry.register(ActionName.SWITCH_PANE, handler)

    assert registry.has(ActionName.SWITCH_PANE)
    assert not registry.has(ActionName.SEND_ENTER)


@pytest.mark.asyncio
async def test_action_registry_dispatch(action_ctx: ActionContext) -> None:
    """Test ActionRegistry.dispatch calls the handler."""
    registry = ActionRegistry()
    handler = AsyncMock()
    registry.register(ActionName.SWITCH_PANE, handler)

    handled = await registry.dispatch(ActionName.SWITCH_PANE, action_ctx)

    assert handled is True
    handler.assert_called_once_with(action_ctx)


@pytest.mark.asyncio
async def test_action_registry_dispatch_unknown(action_ctx: ActionContext) -> None:
    """Test ActionRegistry.dispatch with an unknown action."""
    registry = ActionRegistry()

    handled = await registry.dispatch(ActionName.SWITCH_PANE, action_ctx)

    assert handled is False


@pytest.mark.asyncio
async def test_action_registry_dispatch_by_string(action_ctx: ActionContext) -> None:
    """Test ActionRegistry.dispatch_by_string."""
    registry = ActionRegistry()
    handler = AsyncMock()
    registry.register(ActionName.SWITCH_PANE, handler)

    handled = await registry.dispatch_by_string("switch_pane", action_ctx)

    assert handled is True
    handler.assert_called_once_with(action_ctx)


@pytest.mark.asyncio
async def test_action_registry_dispatch_by_string_unknown(action_ctx: ActionContext) -> None:
    """Test ActionRegistry.dispatch_by_string with an unknown name."""
    registry = ActionRegistry()

    handled = await registry.dispatch_by_string("invalid_action", action_ctx)

    assert handled is False


def test_action_registry_with_builtins() -> None:
    """Test ActionRegistry.with_builtins loads all handlers."""
    registry = ActionRegistry.with_builtins()
    for name in ActionName:
        assert registry.has(name), f"Missing handler for {name}"


@pytest.mark.asyncio
async def test_builtin_handlers_call_tmux(action_ctx: ActionContext) -> None:
    """Test that all built-in handlers call run_tmux or send_keys."""
    from gamux.actions.builtin import BUILTIN_HANDLERS

    with (
        patch.object(ActionContext, "run_tmux", new_callable=AsyncMock) as mock_run_tmux,
        patch.object(ActionContext, "send_keys", new_callable=AsyncMock) as mock_send_keys,
    ):
        for name, handler in BUILTIN_HANDLERS.items():
            mock_run_tmux.reset_mock()
            mock_send_keys.reset_mock()
            await handler(action_ctx)
            # Each handler should call either run_tmux or send_keys (or do nothing like PTT)
            # We don't need to assert exact calls for all, just that they were called if expected.
            if name not in [ActionName.PTT_START, ActionName.PTT_STOP]:
                assert mock_run_tmux.called or mock_send_keys.called
