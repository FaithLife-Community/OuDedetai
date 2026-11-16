# ARCHITECTURE.md

## Module map

- [ou_dedetai/app.py](ou_dedetai/app.py) — abstract `App` (ABC). Provides
  `ask()`/`approve()`/`info()`/`status()`/`exit()`, threading via `start_thread()`,
  config-update hooks, and `self.conf` / `self.logos` handles. Concrete UIs implement
  `_ask()`/`_info()`/`_status()`.
- UI implementations:
  - [ou_dedetai/cli.py](ou_dedetai/cli.py) — `CLI`
  - [ou_dedetai/tui_app.py](ou_dedetai/tui_app.py) — `TUI` (curses/dialog)
  - [ou_dedetai/gui_main.py](ou_dedetai/gui_main.py) — `MainWindow` (Qt/PySide6): simple view,
    install guide, full view (Home/Settings/Troubleshooting), tray. Background work reports back
    through the `Signals` object; see [NEXT.md](NEXT.md).
  - [ou_dedetai/gui_app.py](ou_dedetai/gui_app.py) + [ou_dedetai/gui.py](ou_dedetai/gui.py) — `GuiApp`
    base (prompts, licence dialog) and the "Choose options" installer dialog;
    [ou_dedetai/gui_style.py](ou_dedetai/gui_style.py) — palette and stylesheet;
    [ou_dedetai/i18n](ou_dedetai/i18n) — translations
- [ou_dedetai/main.py](ou_dedetai/main.py) — entry point / dispatcher.
- Domain modules:
  - [ou_dedetai/installer.py](ou_dedetai/installer.py) — install orchestration (`ensure_*` functions)
  - [ou_dedetai/wine.py](ou_dedetai/wine.py) — Wine integration
  - [ou_dedetai/system.py](ou_dedetai/system.py) — subprocess and platform detection
  - [ou_dedetai/logos.py](ou_dedetai/logos.py) — `LogosManager` lifecycle and `State` enum
  - [ou_dedetai/config.py](ou_dedetai/config.py) — Legacy/Persistent/Ephemeral config dataclasses
  - [ou_dedetai/constants.py](ou_dedetai/constants.py) — paths, RUNMODE, version
  - [ou_dedetai/database.py](ou_dedetai/database.py) — SQLite context managers
  - [ou_dedetai/wine_settings.py](ou_dedetai/wine_settings.py) — the Wine settings Ou Dedetai applies,
    with reasons, and a read-back from the prefix's registry files
  - [ou_dedetai/desktop_integrations.py](ou_dedetai/desktop_integrations.py) — offers/installs the
    Logos desktop integrations and calls their backend (a separate program)
  - Others: `network.py` (incl. the offline gate), `backup.py`, `control.py` (incl. purge),
    `repair.py`, `utils.py`, `msg.py`
- **Version source of truth:** `ou_dedetai.constants.LLI_CURRENT_VERSION` —
  [pyproject.toml](pyproject.toml) reads the package version from this attribute.

## Operations pattern

Operations are UI-agnostic domain functions that take `app: App`, call
`app.ask()`/`app.status()`/`app.approve()` for user interaction, and mutate
`app.conf` for persistence. The UI layer calls them; it never implements them.

| Module | Purpose |
|--------|---------|
| `installer.py` | Chained `ensure_*` steps; `install(app)` is the top-level sequencer |
| `control.py` | Post-install actions: uninstall, repair index, get support, edit file |
| `logos.py` / `LogosManager` | Start/stop/index the Logos process; owns `State` enum (RUNNING/STOPPED/STARTING/STOPPING) |
| `backup.py` / `repair.py` | Backup/restore and installation repair detection |
| `wine.py` | Wine process execution and configuration |

## Shared state

All mutable state lives on the `App` instance:

- **`app.conf: Config`** — three-layer config:
  - `_raw: PersistentConfiguration` — JSON on disk (`~/.config/FaithLife-Community/oudedetai.json`, overridable via `$CONFIG_FILE`); every mutation calls `_write()`.
  - `_overrides: EphemeralConfiguration` — CLI args / env vars; never persisted.
  - `_network: NetworkRequests` ([network.py](ou_dedetai/network.py)) — download/version-check cache (`network.json`, 12h lifetime).
- **`app.logos: LogosManager`** — process-lifecycle state (PIDs, `State` enum).

Config mutations fire `config_updated_hooks` via a background daemon thread
watching `_config_updated_event`. UIs subscribe to redraw on change.

## Control flow

```
main() → setup_config() → run(ephemeral_config, action)
  → App subclass.__init__   # loads Config + LogosManager, starts hooks daemon
  → UI event / user action
      → operation(app)              # e.g. installer.install, logos.start
          → app.ask/status/approve  # dispatched to _ask/_status/_info
          → app.conf mutation       # triggers hooks → UI redraws
```

| UI | Interaction model | Notable detail |
|----|-------------------|----------------|
| `CLI` | Stdout + blocking stdin in a background thread | Queues hand prompts/responses across threads |
| `TUI` | Curses screens (`MenuScreen`, `ConsoleScreen`, `HeaderScreen`) | Menu choices call operations directly |
| `GuiApp` | Tkinter `InstallerWindow` + `ControlWindow` | Callbacks dispatch operations via `start_thread()` |
