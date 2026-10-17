# Repository Guidelines

## Project Overview

串口提示助手 (Serial Port Assistant) — a Windows system-tray desktop app that monitors USB serial-port plug/unplug events and surfaces them via a floating ball + translucent card UI. Written in Python 3.13 with PySide6 (Qt6) and pyserial. UI text is Chinese. Ships as a single-file PyInstaller exe (`dist/串口提示助手.exe`).

## Architecture & Data Flow

Plain PySide6 app — **no QMainWindow**. Four top-level objects are constructed and wired in `main.py:main()`:

```
Windows device broadcast (WM_DEVICECHANGE 0x0219)
  → SerialMonitor.event_filter (serial_monitor.py, QAbstractNativeEventFilter)
  → SerialMonitor.schedule_refresh()               — 200ms single-shot timer, coalesces bursts
  → SerialMonitor.refresh()                        — diffs {device: PortInfo} snapshot vs pyserial list_ports.comports()
  → Signal port_added / port_removed(str device, str desc)
  → main.py slots: card.update_ports(ports, details) + card.add_notification(...) + ball.set_port_count() + ball.flash()
  → card auto-shows via ball.show_card() when hidden
```

- **Event capture is owned by `SerialMonitor`** (composed `_DeviceChangeFilter`), not by any widget — the monitor works even if the ball is removed. Filter is installed via `app.installNativeEventFilter(monitor.event_filter)`.
- **Fallback polling**: `SerialMonitor` also runs a `QTimer` (default `POLL_INTERVAL_MS = 1000`) calling `refresh()` — detection is not exclusively event-driven. Every tick first runs the cheap `_cheap_port_names()` pre-check (`QueryDosDevice`, ~0.12 ms vs ~12.6 ms for a full pyserial enumeration) and skips enumeration when the COM set is unchanged, so a high poll rate costs almost nothing and never touches the registry.
- **Fast-path refresh**: `schedule_refresh()` (on `WM_DEVICECHANGE`) runs that same pre-check first; if the COM set already changed it refreshes immediately (~13 ms to notification) instead of waiting out `DEVICE_CHANGE_DELAY_MS`, then still schedules the delayed re-check to backfill description / VID:PID.
- **Response profiles**: `perf_profile.py` maps 自动/省电/均衡/敏捷 → `{poll_ms, event_delay_ms, anim_fps}`; 自动 follows `on_battery()` (AC → 均衡, battery → 省电). `main.apply_perf_profile()` applies them via `monitor.set_timings()` + `ball.set_anim_fps()` at startup, on settings preview, and every `POWER_CHECK_INTERVAL_MS` (30 s). `FloatBall.set_anim_fps()` freezes the animation phase when fps ≤ `STATIC_FPS_MAX` (10) — the 省电 profile keeps only a 5 fps tick to expire event bubbles.
- **Enumeration failure safety**: `_snapshot()` catches exceptions, logs, returns `None`; `refresh()` then keeps the old state — no false removals, no crash.
- **Manual refresh**: card refresh button → `CardWindow.refresh_requested` → `main.on_refresh` → `monitor.refresh()` + `update_ports(..., force=True)` (bypasses the content-signature cache and rebuilds rows — fixes ghost rows).
- **Persistence**: `AliasStore` keeps `{COM口: 备注名}` in `port_aliases.json`; `AppConfig` keeps user settings in `config.json`; both write immediately on change, load at startup, and live next to the exe (`app_paths.data_dir()` — `dirname(sys.executable)` when frozen; PyInstaller one-file makes `__file__` unreliable, always use `sys.executable`).
- **Logging**: rotating `app.log` (1MB) next to the exe; `sys.excepthook` logs unhandled exceptions and shows a message box. Module loggers use `logging.getLogger(__name__)`.
- **Single instance**: `QLockFile` in the temp dir; a second launch shows a message and exits.
- **Styling**: theme system in `themes.py` — ball (gradient/text/flash colors) and card (panel/border/text/row/notification palettes) are independently selectable, plus card style (卡片/气泡/极简) and radius 0–24 (0=直角). CardWindow QSS and FloatBall painting read the config at `apply_theme()` time; the settings dialog applies changes instantly. Translucency stays simulated (`WA_TranslucentBackground` + QSS rgba), no DWM dependency.

## Key Directories

| Path | Purpose |
|---|---|
| `main.py` | Entry point: object construction, all signal wiring, tray menu (显示/设置/开机自启/退出), logging, single-instance lock |
| `card_window.py` | `CardWindow` (translucent port list), `PortRow`, `NotificationItem` (auto-fade, configurable lifetime) |
| `float_ball.py` | `FloatBall`: 56px draggable ball, paint/flash animation, right-click context menu (shares the tray `QMenu` instance via `set_context_menu`) |
| `serial_monitor.py` | `SerialMonitor` (QObject): port enumeration + diff, `PortInfo` dataclass, `_DeviceChangeFilter` (native event capture) |
| `usb_popup.py` | `UsbPopup`: centered USB 3D splash painted with QPainter (Ease-out-back), duration from `popup_duration_ms` |
| `mascots.py` | Cartoon mascot painting (小奶龙 / 大白): image from `assets/mascots/` or pure QPainter, with speech bubble showing the port count |
| `com_manager.py` | 串口号管理核心：注册表 `ComDB` 位图读写、设备实例列举、清理幽灵口 / 固定口号 / 备份恢复、UAC 提权子任务（`try_run_com_task` 在 `main()` 最前处理 `--com-task`） |
| `com_manager_dialog.py` | `ComManagerDialog`：串口号管理对话框（状态 / 串口号 / 设备表格 + 清理 / 固定 / 恢复备份） |
| `perf_profile.py` | 响应档位注册表 `{poll_ms, event_delay_ms, anim_fps}`、`on_battery()` 电源判定、`resolve()`（非法值回退默认） |
| `alias_store.py` | `AliasStore`: JSON persistence of port aliases |
| `app_config.py` | `AppConfig`: user settings (notify lifetime / auto-show / notify-on-remove), JSON persistence, type coercion |
| `app_paths.py` | `data_dir()`/`data_file()`: exe-adjacent data directory (frozen-aware) |
| `autostart.py` | `Autostart`: HKCU Run-key toggle; `build_run_value()` pure helper (exe vs pythonw+main.py) |
| `settings_dialog.py` | `SettingsDialog`：外观（球/卡片主题、卡片风格、圆角、宽度、字体/字号/颜色）+ 通知，改动即时生效；可编辑字体下拉框（选择或手输） |
| `themes.py` | 外观主题注册表：6 组悬浮球主题、6 组卡片主题、3 种卡片风格；`resolve_radius()` 按风格解析圆角 |
| `tools/make_icon.py` | Generates `assets/icon.ico` (ball + 「串」, ICO-embedded PNG, no deps) |
| `tests/` | pytest suite (31 tests) — pure logic, offscreen Qt |
| `.spec-workflow/` | Spec-driven development config: templates for steering docs and requirements/design/tasks specs; `user-templates/` overrides defaults; empty `steering/ specs/ approvals/ archive/` dirs |
| `.opencode/` | opencode plugin SDK scaffolding, ignore |
| `dist/`, `build/` | PyInstaller output; regenerated, never edit |

## Development Commands

```powershell
# install runtime deps
pip install -r requirements.txt          # PySide6>=6.6, pyserial>=3.5

# install dev deps (tests)
pip install -r requirements-dev.txt      # adds pytest>=8

# run tests (headless, offscreen Qt — no display needed)
python -m pytest tests/ -q

# run app (Windows GUI)
python main.py

# regenerate icon (only when changing the design)
python tools/make_icon.py

# build single-file exe (icon from assets/icon.ico, console=False)
pyinstaller 串口提示助手.spec
```

Runtime: **Python 3.13, Windows only**. No Python lockfile, no lint/type-check gate (basedpyright strict-mode warnings are expected noise — the project intentionally has no type hints).

## Code Conventions & Common Patterns

- **Chinese docstrings** on every module, class, and public method; inline comments in Chinese.
- **No type hints** on public APIs except dataclasses (`PortInfo`) and a few pure helpers where the analyzer needs them; payload types documented in docstrings (e.g. `ports: {device: description}`).
- **Module-level constants** in UPPER_SNAKE: `POLL_INTERVAL_MS`, `DEVICE_CHANGE_DELAY_MS`, `NOTIFY_LIFETIME_MS`, `FADE_IN_MS/FADE_OUT_MS`, `DEFAULT_ANIM_FPS`, `STATIC_FPS_MAX`, `ALPHA_MIN/MAX/DEFAULT`. Anything a response profile can override lives in `perf_profile.PROFILES`; the module constant is only the fallback default.
- **Qt signals** as class attributes with Chinese payload comments: `port_added = Signal(str, str)` / `refresh_requested = Signal()` / `edit_requested = Signal(str)`. Request-style naming (`xxx_requested`) for outbound "please do X" signals; wiring always lives in `main.py`, never inside widgets.
- **Error handling**: swallow-and-degrade, never crash the GUI. File I/O: `except (OSError, ValueError)` then **log via `logger.exception(...)`** (don't silently pass). Native/OS paths: `except OSError`.
- **Config-driven behavior**: user-tunable values go through `AppConfig` (see `DEFAULTS`), read at event time in `main.py` so changes apply live; don't hardcode new timings. Appearance keys: `ball_theme` / `card_theme` / `card_style` / `card_radius` / `card_width` / `font_family` (empty=system) / `font_size` (8–18, title/count derive ±2/-1) / `font_color` (empty=theme). **Adding a theme** = one entry in `themes.BALL_THEMES`/`CARD_THEMES`/`CARD_STYLES` (all keys required — enforced by `tests/test_themes.py`). Font family propagates via `setFont()` (children inherit); QSS only overrides derived sizes.
- **Widget styling** via `setObjectName(...)` + QSS strings (`#cardPanel`, `#notifyItem`); animation via `QPropertyAnimation` with `_get_/_set_` properties.
- **Deferred layout work** after `deleteLater()` via `QTimer.singleShot(0, ...)`.
- **Natural COM-port ordering**: `CardWindow._port_sort_key` sorts numeric suffixes numerically (`COM10` after `COM2`); reuse for any port ordering.
- Debounce OS event bursts with a **single-shot QTimer + `start()`** (restart semantics), not piled-up `singleShot`s.

## Important Files

- `main.py` — the only wiring point; new cross-component connections go here
- `串口提示助手.spec` — PyInstaller one-file spec, `console=False`, `icon='assets/icon.ico'`, no hidden imports/datas
- `serial_monitor.py` — `PortInfo` (device/desc/vid/pid/manufacturer/serial_number/hwid) is the rich data model; `ports` (desc map) for list/count, `details` (PortInfo map) for tooltips
- `themes.py` — appearance registry; `CardWindow.apply_theme()` and `FloatBall.apply_theme()` are the single points that restyle from config (preview callback in `main.on_preview`)
- `port_aliases.json` / `config.json` — runtime data next to the exe; not bundled by the spec (created at runtime)
- `.spec-workflow/templates/` — expected workflow: requirements (numbered IDs) → design → tasks docs written **before** implementation; task templates embed agent prompts

## Testing & QA

- **pytest suite in `tests/`** (100 tests, all headless): `SerialMonitor` diff/failure/coalescing/event-filter + `set_timings`/fast-path pre-check, `AliasStore` persistence, `AppConfig` coercion, `com_manager` ComDB bitmap/device listing/clear+assign/backup-restore/elevation command line, `perf_profile` table completeness/monotonicity/power-source resolve/fallback, `CardWindow` rebuild cache + force + sort, theme registry completeness/radius/applied-QSS/dialog instant-apply/typography (font family/size/color/width) + response-profile combo, `Autostart` value building, `QLockFile` exclusivity, icon validity + spec reference, full-wiring smoke.
- Fixtures: `tests/conftest.py` forces `QT_QPA_PLATFORM=offscreen` before importing Qt.
- Test style: inject snapshots / patch `list_ports.comports` — never touch real hardware or the real registry.
- Manual verification for GUI-only behavior: `python main.py`, plug/unplug a USB serial device, confirm card/ball/notifications, aliases + settings persist across restart, second instance is blocked, tray settings/autostart work.
- Build verification: `pyinstaller 串口提示助手.spec`, run `dist/串口提示助手.exe`, confirm `port_aliases.json`/`config.json`/`app.log` appear next to the exe.

<!-- TRELLIS:START -->
# Trellis Instructions

These instructions are for AI assistants working in this project.

This project is managed by Trellis. The working knowledge you need lives under `.trellis/`:

- `.trellis/workflow.md` — development phases, when to create tasks, skill routing
- `.trellis/spec/` — package- and layer-scoped coding guidelines (read before writing code in a given layer)
- `.trellis/workspace/` — per-developer journals and session traces
- `.trellis/tasks/` — active and archived tasks (PRDs, research, jsonl context)

If a Trellis command is available on your platform (e.g. `/trellis:finish-work`, `/trellis:continue`), prefer it over manual steps. Not every platform exposes every command.

If you're using Codex or another agent-capable tool, additional project-scoped helpers may live in:
- `.agents/skills/` — reusable Trellis skills
- `.codex/agents/` — optional custom subagents

Managed by Trellis. Edits outside this block are preserved; edits inside may be overwritten by a future `trellis update`.

<!-- TRELLIS:END -->
