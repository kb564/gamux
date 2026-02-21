"""XDG-compliant runtime paths and WSL2 gateway detection."""

from __future__ import annotations

import os
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path


def runtime_dir() -> Path:
    """Return XDG_RUNTIME_DIR/gamux or fallback to /tmp/gamux-<uid>."""
    xdg = os.environ.get("XDG_RUNTIME_DIR")
    p = Path(xdg) / "gamux" if xdg else Path(tempfile.gettempdir()) / f"gamux-{os.getuid()}"
    p.mkdir(parents=True, exist_ok=True)
    return p


def rumble_fifo() -> Path:
    """Return the path to the rumble FIFO."""
    return runtime_dir() / "rumble.fifo"


def config_dir() -> Path:
    """Return ~/.config/gamux, creating it if needed."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    p = Path(xdg) / "gamux" if xdg else Path.home() / ".config" / "gamux"
    p.mkdir(parents=True, exist_ok=True)
    return p


def default_config_path() -> Path:
    """Return the default config file path."""
    return config_dir() / "config.toml"


@lru_cache(maxsize=1)
def wsl_gateway() -> str | None:
    """Detect the WSL2 host gateway IP. Returns None if not in WSL2."""
    try:
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if parts and parts[0] == "default":
                idx = parts.index("via") + 1 if "via" in parts else None
                if idx is not None:
                    return parts[idx]
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass
    return None


def is_wsl2() -> bool:
    """Return True if running inside WSL2."""
    try:
        kernel = Path("/proc/version").read_text()
        return "microsoft" in kernel.lower() or "wsl" in kernel.lower()
    except OSError:
        return False
