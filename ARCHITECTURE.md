# ARCHITECTURE.md

## Module map

- [ou_dedetai/app.py](ou_dedetai/app.py) — abstract `App` (ABC). Provides
  `ask()`/`approve()`/`info()`/`status()`/`exit()`, threading via `start_thread()`,
  config-update hooks, and `self.conf` / `self.logos` handles. Concrete UIs implement
  `_ask()`/`_info()`/`_status()`.
- UI implementations:
  - [ou_dedetai/cli.py](ou_dedetai/cli.py) — `CLI`
  - [ou_dedetai/tui_app.py](ou_dedetai/tui_app.py) — `TUI` (Textual)
  - [ou_dedetai/gui/](ou_dedetai/gui/) — the Qt (PySide6) window:
    - [window.py](ou_dedetai/gui/window.py) — `MainWindow`: its views (simple, install guide, full
      view with Home/Settings/Troubleshooting), pages and refresh. Background work reports back
      through the `Signals` object; see [NEXT.md](NEXT.md).
    - [mixins/](ou_dedetai/gui/mixins/) — one mixin per feature, which `MainWindow` inherits: simple
      view, Home, Settings, Troubleshooting, install, Logos, updates, Wine builds, integrations,
      Akousousin. [mixins/base.py](ou_dedetai/gui/mixins/base.py) lists what they use from the
      window and from each other (for mypy; an empty class at run time).
    - [blocks.py](ou_dedetai/gui/blocks.py) (labels, buttons, cards, rows),
      [install_guide.py](ou_dedetai/gui/install_guide.py), [tray.py](ou_dedetai/gui/tray.py),
      [close_dialog.py](ou_dedetai/gui/close_dialog.py).
    - [app.py](ou_dedetai/gui/app.py) + [widgets.py](ou_dedetai/gui/widgets.py) — `GuiApp` base
      (prompts, licence dialog) and the "Choose options" installer dialog;
      [style.py](ou_dedetai/gui/style.py) — palette and stylesheet.
  - [ou_dedetai/i18n](ou_dedetai/i18n) — the window's translations
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
| `TUI` | Textual screens (menus, console, prompts) | Menu choices call operations directly |
| `MainWindow` (`GuiApp`) | Qt window: simple view, install guide, full view; tray while Logos runs | Operations run via `start_thread()`; results come back to the window through `Signals` |

## Use these instead of writing your own

Most operations need one of these; adding a second way to do the same thing is the
most common review comment.

| Need | Use |
|------|-----|
| Download a file or fetch a URL (progress, retries, offline mode) | `network.logos_reuse_download` (cached, size-checked), or `network._net_get` |
| Latest release of a GitHub project | `app.conf._network._repo_version` (cached 12 h) or `network._get_release_data` (fresh) |
| Run Wine or a Windows program in the prefix | `wine.run_wine_process` / `run_wine_during_install` (waits, logs, raises on failure) |
| Run any other program | `system.run_program` (system libraries, not the binary's bundled ones) or `system.run_command` |
| Read the prefix's registry (no Wine process) | `wine.read_registry`, `wine.reg_string`; write one value with `wine.reg_add` |
| Offer a system package a feature needs | `system.offer_packages` (never on image-based systems) |
| Compare release versions | `utils.is_newer_version` |
| Is Wine our oinos build? | `wine.wine_supports_logos_updates(wine.get_wine_release(binary)[0])` (cached per binary) |
| Is anything still running in the prefix? | `wine.leftover_wine`; end it with `wine.wineserver_kill` |
