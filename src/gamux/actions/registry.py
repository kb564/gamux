"""ActionRegistry — maps ActionName to handler functions."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from gamux.actions.context import ActionContext
from gamux.actions.names import ActionName

logger = logging.getLogger(__name__)

ActionHandler = Callable[[ActionContext], Awaitable[None]]


class ActionRegistry:
    """Maps ActionName -> async handler. Supports string lookup for config bindings."""

    def __init__(self) -> None:
        self._handlers: dict[ActionName, ActionHandler] = {}

    def register(self, name: ActionName, handler: ActionHandler) -> None:
        """Register a handler for an action."""
        self._handlers[name] = handler

    def register_all(self, handlers: dict[ActionName, ActionHandler]) -> None:
        """Register multiple handlers at once."""
        self._handlers.update(handlers)

    def has(self, name: ActionName) -> bool:
        """Return True if a handler is registered for this action."""
        return name in self._handlers

    async def dispatch(self, name: ActionName, ctx: ActionContext) -> bool:
        """Dispatch an action. Returns True if handled, False if unknown."""
        handler = self._handlers.get(name)
        if handler is None:
            logger.warning("No handler registered for action: %s", name)
            return False
        try:
            await handler(ctx)
            return True
        except Exception:
            logger.exception("Error in action handler: %s", name)
            return False

    async def dispatch_by_string(self, action_str: str, ctx: ActionContext) -> bool:
        """Dispatch by string name (from config bindings). Logs warning for unknown names."""
        try:
            name = ActionName(action_str)
        except ValueError:
            logger.warning("Unknown action name in binding: %r", action_str)
            return False
        return await self.dispatch(name, ctx)

    @classmethod
    def with_builtins(cls) -> ActionRegistry:
        """Create a registry pre-loaded with all built-in handlers."""
        from gamux.actions.builtin import BUILTIN_HANDLERS

        registry = cls()
        registry.register_all(BUILTIN_HANDLERS)
        return registry
