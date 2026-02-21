# Gamux

Control [tmux](https://github.com/tmux/tmux) with a game controller and voice recognition.

Hold **ZL** and speak → your words are transcribed and sent to the active pane.
Press **ZL + button** → switch panes, send keys, or trigger any mapped action.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## Requirements

| Component | Details |
|-----------|---------|
| OS | Linux (or WSL2 on Windows) |
| Python | 3.11+ |
| Controller | USB/Bluetooth gamepad (Nintendo Switch 2 Pro Controller recommended) |
| tmux | Any recent version |
| Microphone | Local mic **or** Windows mic via [Bridge service](#bridge-service-wsl2) |

---

## Installation

```bash
git clone https://github.com/kb564/gamux
cd gamux
pip install -e ".[dev]"
```

---

## Quick Start

```bash
# Check your setup
gamux doctor

# Run with default config
gamux run

# Run with a custom config file
gamux run --config ~/.config/gamux/config.toml
```

---

## Configuration

Gamux looks for a config file at `~/.config/gamux/config.toml` by default.

```toml
[controller]
device_path = ""        # empty = auto-detect
grab = false            # exclusively grab the device
stick_deadzone = 0.1

[voice]
model = "small"         # tiny / base / small / medium / large-v3
language = "ja"
compute_type = "int8"   # int8 / float16 / float32
beam_size = 5

[tmux]
command_timeout = 5.0

[bridge]
host = ""               # empty = auto-detect WSL2 gateway
port = 8765

[rumble]
enabled = true

[bindings]
ZL_A         = "switch_pane_right"
ZL_B         = "switch_pane_down"
ZL_X         = "switch_pane_up"
ZL_Y         = "switch_pane_left"
ZL_R         = "switch_window_next"
ZL_L         = "switch_window_prev"
ZL_plus      = "send_enter"
ZL_minus     = "send_escape"
ZL_dpad_up   = "scroll_up"
ZL_dpad_down = "scroll_down"
```

### Validate config

```bash
gamux config validate
gamux config show        # print effective config as TOML
```

---

## Built-in Actions

| Action | Description |
|--------|-------------|
| `switch_pane` | Cycle to next pane |
| `switch_pane_up/down/left/right` | Directional pane switch |
| `switch_window_next/prev` | Next/previous tmux window |
| `send_enter` | Send Enter key |
| `send_escape` | Send Escape key |
| `send_ctrl_c` | Send Ctrl+C |
| `scroll_up/down` | Scroll in copy mode |
| `copy_mode` | Enter tmux copy mode |
| `paste` | Paste from tmux buffer |
| `ptt_start/ptt_stop` | Push-to-talk (internal) |

---

## Analog Stick Calibration

If your stick drifts, calibrate the neutral position:

```bash
gamux calibrate
```

---

## Bridge Service (WSL2)

When running in WSL2, Gamux cannot access the Windows microphone directly.
The **Bridge service** runs on Windows and streams mic audio to WSL2 over WebSocket.

### Windows setup

```powershell
# Install Python dependencies on Windows
pip install sounddevice websockets numpy

# Start the bridge
python bridge/service.py

# Or install as a Task Scheduler service (auto-start on login)
# Run as Administrator:
powershell -ExecutionPolicy Bypass -File bridge/install-windows-service.ps1
```

### WSL2 Gamux config

Gamux auto-detects the Windows gateway IP. To specify manually:

```toml
[bridge]
host = "172.x.x.x"   # your WSL2 gateway IP
port = 8765
```

---

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]" pytest-cov

# Run tests
pytest tests/

# Run tests with coverage
pytest tests/ --cov=src/gamux --cov-report=term-missing

# Lint
ruff check src/ bridge/ tests/
ruff format src/ bridge/ tests/

# Type check
mypy src/gamux/
```

---

## Project Structure

```
src/gamux/
├── config.py          # Pydantic v2 configuration
├── paths.py           # XDG-compliant paths + WSL2 detection
├── cli.py             # typer CLI (run/doctor/config/calibrate)
├── app.py             # Main application class
├── tmux.py            # tmux command wrapper
├── rumble.py          # Rumble feedback manager
├── status.py          # Status display (tmux window name)
├── controller/
│   ├── buttons.py     # ButtonName / AnalogAxis enums + evdev maps
│   └── reader.py      # Async controller event reader
├── voice/
│   ├── source.py      # AudioSource (Local + Bridge)
│   ├── vad.py         # Voice Activity Detection
│   └── recognizer.py  # faster-whisper transcription
└── actions/
    ├── names.py        # ActionName enum
    ├── context.py      # ActionContext (tmux helpers)
    ├── registry.py     # ActionRegistry (dispatch)
    └── builtin.py      # Built-in action handlers

bridge/
├── service.py         # Windows bridge (WebSocket audio server)
└── config.toml        # Bridge service config
```

---

## License

[MIT](LICENSE)
