"""Gamux CLI — typer-based entry point."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(
    name="gamux",
    help="Control tmux with a game controller and voice recognition.",
    no_args_is_help=True,
)
config_app = typer.Typer(help="Configuration commands.")
app.add_typer(config_app, name="config")


# --- Run ---


@app.command()
def run(
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to config file."),
    ] = None,
    override: Annotated[
        Path | None,
        typer.Option("--override", "-o", help="Override TOML to merge on top of config."),
    ] = None,
    debug: Annotated[bool, typer.Option("--debug", help="Enable debug logging.")] = False,
) -> None:
    """Start Gamux."""
    _setup_logging(debug)
    from gamux.app import App
    from gamux.config import AppConfig

    cfg = AppConfig.load_with_override(base=config, override=override)
    application = App(cfg)

    async def _main() -> None:
        await application.setup()
        try:
            await application.run()
        finally:
            await application.shutdown()

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_main())


# --- Doctor ---


@app.command()
def doctor(
    json_output: Annotated[bool, typer.Option("--json", help="Output results as JSON.")] = False,
) -> None:
    """Check system requirements and configuration."""
    results: list[dict[str, str]] = []

    def check(name: str, fn: object) -> bool:
        try:
            fn()  # type: ignore[operator]
            results.append({"name": name, "status": "ok"})
            return True
        except Exception as e:
            results.append({"name": name, "status": "fail", "message": str(e)})
            return False

    def _check_evdev() -> None:
        import evdev

        devices = evdev.list_devices()
        if not devices:
            raise RuntimeError("No input devices found. Is the controller connected?")

    def _check_tmux() -> None:
        import subprocess

        result = subprocess.run(
            ["tmux", "display-message", "-p", ""], capture_output=True, timeout=3
        )
        if result.returncode != 0:
            raise RuntimeError("tmux is not running or not accessible.")

    def _check_faster_whisper() -> None:
        import faster_whisper  # noqa: F401

    def _check_sounddevice() -> None:
        import sounddevice as sd

        devices = sd.query_devices()
        if not devices:
            raise RuntimeError("No audio devices found.")

    def _check_config() -> None:
        from gamux.config import AppConfig
        from gamux.paths import default_config_path

        path = default_config_path()
        if path.exists():
            AppConfig.load(path)
        # No config file is fine — defaults are used

    check("evdev", _check_evdev)
    check("tmux", _check_tmux)
    check("faster-whisper", _check_faster_whisper)
    check("sounddevice", _check_sounddevice)
    check("config", _check_config)

    if json_output:
        typer.echo(json.dumps(results, indent=2))
    else:
        all_ok = True
        for result in results:
            status = result["status"]
            message = result.get("message", "")
            icon = "✓" if status == "ok" else "✗"
            line = f"  {icon} {result['name']}"
            if message:
                line += f": {message}"
            typer.echo(line)
            if status != "ok":
                all_ok = False
        if not all_ok:
            raise typer.Exit(code=1)


# --- Config subcommands ---


@config_app.command("show")
def config_show(
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to config file."),
    ] = None,
) -> None:
    """Show effective configuration as TOML."""
    try:
        import tomli_w  # type: ignore[import-untyped]

        has_tomli_w = True
    except ImportError:
        has_tomli_w = False

    from gamux.config import AppConfig

    cfg = AppConfig.load(config)
    data = cfg.model_dump()

    if has_tomli_w:
        typer.echo(tomli_w.dumps(data))
    else:
        # Fallback: pretty JSON
        typer.echo(json.dumps(data, indent=2, default=str))


@config_app.command("validate")
def config_validate(
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to config file."),
    ] = None,
) -> None:
    """Validate configuration file and report errors."""
    from pydantic import ValidationError

    from gamux.config import AppConfig
    from gamux.paths import default_config_path

    path = config or default_config_path()
    if not path.exists():
        typer.echo(f"Config file not found: {path}")
        typer.echo("Using defaults — no validation errors.")
        return

    try:
        cfg = AppConfig.load(path)
        typer.echo(f"✓ Config valid: {path}")
        typer.echo(f"  voice.model = {cfg.voice.model}")
        typer.echo(f"  bindings    = {len(cfg.bindings)} entries")
    except ValidationError as e:
        typer.echo(f"✗ Config validation failed: {path}", err=True)
        for error in e.errors():
            loc = " -> ".join(str(item) for item in error["loc"])
            typer.echo(f"  [{loc}] {error['msg']}", err=True)
        raise typer.Exit(code=1) from e


# --- Calibrate ---


@app.command()
def calibrate(
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to config file."),
    ] = None,
) -> None:
    """Interactively calibrate analog stick neutral position."""
    import tomllib

    import evdev

    typer.echo("=== Gamux Stick Calibration ===")
    typer.echo("This will measure your controller's analog stick neutral (center) values.")

    # Find device
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    gamepads = [
        device
        for device in devices
        if any(
            "BTN_SOUTH" in str(key) or "BTN_A" in str(key)
            for key in device.capabilities(verbose=True).get(("EV_KEY", 1), [])
        )
    ]

    if not gamepads:
        typer.echo("✗ No gamepad found. Connect your controller and try again.", err=True)
        raise typer.Exit(code=1)

    device = gamepads[0]
    typer.echo(f"Using device: {device.name} ({device.path})")
    typer.echo("\nRELEASE both analog sticks to neutral position, then press ENTER.")
    input()

    # Sample absolute positions
    abs_info = device.capabilities().get(evdev.ecodes.EV_ABS, [])
    axis_map = {0: "left_x", 1: "left_y", 2: "right_x", 5: "right_y"}
    neutral: dict[str, int] = {}

    for code, info in abs_info:
        if code in axis_map:
            neutral[axis_map[code]] = info.value

    if not neutral:
        typer.echo(
            "✗ Could not read axis values. Is the controller reporting ABS events?", err=True
        )
        raise typer.Exit(code=1)

    typer.echo("\nMeasured neutral values:")
    for axis, value in neutral.items():
        typer.echo(f"  {axis}: {value}")

    # Average x and y separately
    x_keys = ["left_x", "right_x"]
    y_keys = ["left_y", "right_y"]
    x_count = max(1, sum(1 for key in x_keys if key in neutral))
    y_count = max(1, sum(1 for key in y_keys if key in neutral))
    neutral_x = int(sum(neutral[key] for key in x_keys if key in neutral) / x_count)
    neutral_y = int(sum(neutral[key] for key in y_keys if key in neutral) / y_count)

    typer.echo("\nRecommended config:")
    typer.echo("  [controller]")
    typer.echo(f"  stick_neutral_x = {neutral_x}")
    typer.echo(f"  stick_neutral_y = {neutral_y}")

    if typer.confirm("\nSave to config file?"):
        from gamux.paths import default_config_path

        target = config or default_config_path()
        data: dict = {}
        if target.exists():
            with target.open("rb") as file:
                data = tomllib.load(file)
        data.setdefault("controller", {})
        data["controller"]["stick_neutral_x"] = neutral_x
        data["controller"]["stick_neutral_y"] = neutral_y

        try:
            import tomli_w  # type: ignore[import-untyped]

            with target.open("wb") as file:
                tomli_w.dump(data, file)
        except ImportError:
            # Fallback: manual TOML write for simple cases
            lines = [
                "[controller]",
                f"stick_neutral_x = {neutral_x}",
                f"stick_neutral_y = {neutral_y}",
            ]
            target.write_text("\n".join(lines) + "\n")

        typer.echo(f"✓ Saved to {target}")


# --- Helpers ---


def _setup_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    if not debug:
        logging.getLogger("faster_whisper").setLevel(logging.WARNING)
