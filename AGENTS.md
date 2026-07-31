# Repository Guidelines

## Project Overview

串口提示助手 (Serial Port Assistant) — a Windows system-tray desktop app that monitors USB serial-port plug/unplug events and surfaces them via a floating ball + translucent card UI. Written in Python 3.13 with PySide6 (Qt6) and pyserial. UI text is Chinese. Ships as a single-file PyInstaller exe (`dist/串口提示助手.exe`).

## Architecture & Data Flow

Plain PySide6 app — **no QMainWindow**. Four top-level objects are constructed and wired in `main.py:main()`:

```
Windows device broadcast (WM_DEVICECHANGE 0x0219)
  → FloatBall.nativeEvent (float_ball.py)          — only place Windows APIs are touched
  → SerialMonitor.schedule_refresh()               — QTimer.singleShot(200ms) waits for driver enumeration
  → SerialMonitor.refresh()                        — diffs {device: description} snapshot vs pyserial list_ports.comports()
  → Signal port_added / port_removed(str device, str desc)
  → main.py slots: card.update_ports() + card.add_notification() + ball.set_port_count() + ball.flash()
  → card auto-shows via ball.show_card() when hidden
```

- **Fallback polling**: `SerialMonitor` also runs a 1s `QTimer` (`POLL_INTERVAL_MS = 1000`) calling `refresh()` — device-change detection is not exclusively event-driven.
- **Manual refresh**: card refresh button → `CardWindow.refresh_requested` signal → `main.on_refresh` → `monitor.refresh()` + forced list rebuild (fixes ghost rows).
- **Persistence**: `AliasStore` keeps `{COM口: 备注名}` in `port_aliases.json`, written immediately on every edit, loaded at startup. When frozen (`sys.frozen`), the file lives next to the exe (`dirname(sys.executable)`); otherwise next to the script. PyInstaller one-file mode makes `__file__` unreliable — always use `sys.executable` for data-file paths.
- **Styling**: translucency is **simulated** via `Qt.WA_TranslucentBackground` + QSS `rgba(...)` backgrounds with a user alpha slider (persisted via `QSettings`). The real DWM acrylic wrapper exists but is unwired — see Important Files.

## Key Directories

| Path | Purpose |
|---|---|
| `main.py` | Entry point: object construction, all signal wiring, tray icon + menu |
| `card_window.py` | `CardWindow` (translucent port list), `PortRow`, `NotificationItem` (auto-fade 20s) |
| `float_ball.py` | `FloatBall`: 56px draggable ball, paint/flash animation, `WM_DEVICECHANGE` hook |
| `serial_monitor.py` | `SerialMonitor` (QObject): port enumeration + diff, plug/unplug signals |
| `alias_store.py` | `AliasStore`: JSON persistence of port aliases |
| `acrylic.py` | **Dead code** — DWM acrylic ctypes wrapper, imported by nothing; do not extend, consider deleting |
| `.spec-workflow/` | Spec-driven development config: templates for product/tech/structure steering docs and requirements/design/tasks specs; `user-templates/` overrides defaults (same filename wins); empty `steering/ specs/ approvals/ archive/` dirs |
| `.opencode/` | opencode plugin SDK scaffolding (`@opencode-ai/plugin`), ignore |
| `dist/`, `build/` | PyInstaller output; regenerated, never edit |

## Development Commands

```powershell
# install
pip install -r requirements.txt          # PySide6>=6.6, pyserial>=3.5

# run (Windows, GUI app — no console output expected)
python main.py

# build single-file exe
pyinstaller 串口提示助手.spec              # --onefile --windowed, console=False
```

Runtime: **Python 3.13, Windows only**. No Python lockfile, no git repo in the workspace, no lint/format config.

## Code Conventions & Common Patterns

- **Chinese docstrings** on every module, class, and public method; inline comments in Chinese. New code should match.
- **No type hints** on public APIs — signatures like `def get(self, device)`; payload types documented in docstrings (e.g. `ports: {device: description}`).
- **Module-level constants** in UPPER_SNAKE for all magic numbers: `POLL_INTERVAL_MS`, `DEVICE_CHANGE_DELAY_MS`, `FADE_OUT_MS`, `ALPHA_MIN/MAX/DEFAULT`.
- **Qt signals** declared as class attributes with payload comments in Chinese:
  `port_added = Signal(str, str)` / `refresh_requested = Signal()` / `closed = Signal(object)  # 携带自身,供卡片收缩/自动隐藏`.
  Request-style naming (`xxx_requested`) for outbound "please do X" signals; wiring always lives in `main.py`, never inside widgets.
- **Error handling**: swallow-and-degrade, never crash the GUI. `except (OSError, ValueError): pass` on file I/O; `except Exception: return False` in native wrappers.
- **Widget styling** via `setObjectName(...)` + QSS stylesheet strings (`#cardPanel`, `#notifyItem`), applied in `_apply_style()`; animation via `QPropertyAnimation` with `_get_/_set_` flash properties.
- **Private members** prefixed `_`; read-only access via `@property` (e.g. `SerialMonitor.ports` returns a dict copy).
- **Deferred layout work** after `deleteLater()` with `QTimer.singleShot(0, ...)`.
- **Natural COM-port ordering**: `_port_sort_key` sorts numeric suffixes numerically (`COM10` after `COM2`); reuse it for any new port ordering.
- Single-window app: no signals with object args cross module boundaries except `NotificationItem.closed` (object payload).

## Important Files

- `main.py` — the only wiring point; new cross-component connections go here
- `串口提示助手.spec` — PyInstaller one-file spec, `console=False`, no hidden imports/datas
- `port_aliases.json` — runtime data (root + dist copies); not bundled by the spec
- `acrylic.py` — unwired DWM acrylic implementation; `CardWindow` deliberately uses QSS translucency instead. Do not "reconnect" it without checking why the QSS approach was chosen (works on more Windows versions, no undocumented APIs).
- `.spec-workflow/templates/` — expected workflow: requirements (numbered IDs) → design → tasks docs written **before** implementation; task templates embed agent prompts. Follow this when the user asks for spec-driven work.

## Testing & QA

- **No tests, no test framework, no CI.** Verification is manual: `python main.py`, plug/unplug a USB serial device (or use `serial_monitor.refresh()`), confirm card list updates, notifications appear/fade, aliases persist across restart, tray quit works.
- After a change, smoke-test the affected path by running the app — don't invent a test harness unless asked.
- Build verification: `pyinstaller 串口提示助手.spec`, run `dist/串口提示助手.exe`, check `port_aliases.json` is created next to the exe.
