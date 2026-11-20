# AGENTS.md

Guidance for AI coding agents working in this repository. For full human-facing
setup instructions see [CONTRIBUTING.md](CONTRIBUTING.md); for the user-facing
overview see [README.md](README.md).

## Project overview

OuDedetai installs and maintains FaithLife's Logos/Verbum Bible software on Linux
via Wine. It is a FaithLife Community project (MIT licensed). The shipped artifact
is a PyInstaller binary with a Qt (PySide6) window, a Textual terminal menu and a
command line. It installs Logos with a bundled Wine build into the user's home folder
(no system packages by default), applies and lists the Wine settings Logos needs,
and creates desktop shortcuts.

## Setup

- Requires **Python 3.12+**; the window needs Qt's X11/Wayland system libraries
  (list in [CONTRIBUTING.md](CONTRIBUTING.md)).
- `./scripts/ensure-python.sh` — builds/installs Python 3.12 if needed.
- `./scripts/ensure-venv.sh` — creates and configures the virtual environment.
- With a 3.12 venv active: `pip install .[dev]` (includes `mypy` and `ruff`).

## Common commands

- **Run:** `python -m ou_dedetai.main --help`
- **Window:** `DIALOG=tk python -m ou_dedetai.main` (from a terminal the default is the TUI)
- **Translations:** `python scripts/update-translations.py` after changing window text
- **Doc screenshots:** `QT_QPA_PLATFORM=offscreen python scripts/make-screenshots.py docs/images`
- **Tests:** `./scripts/run-tests.sh`
- **Lint:** `ruff check`
- **Type check:** `mypy ou_dedetai`
- **Build binary:** `./scripts/build-binary.sh x86_64`

## Testing

- **Framework:** stdlib `unittest` only — no pytest.
- **Location:** [tests/](tests/) — `test_<module>.py` per module (most modules have
  one, including the window in `test_gui_main.py`); add one when you touch a module
  that lacks coverage. `tests/integration.py` holds end-to-end checks.
- **Mocking `App`:** pass `app = unittest.mock.Mock()` and set attributes directly.
  Domain functions take `app: App`; a `Mock` satisfies the interface.
- **No live network in unit tests** — stub `app.conf` attributes instead of hitting
  real URLs (`test_network.py` is the only intentional exception).
- **Test data:** [tests/data/](tests/data/) — static fixtures.

## Conventions

- Follow standard Python idioms and match surrounding code.
- `ruff` enforces only `E`/`F` rules at a 120-char line length (see [pyproject.toml](pyproject.toml)).
- Keep [ou_dedetai/config.py](ou_dedetai/config.py) fully typed — it has a stricter
  mypy override (`disallow_untyped_calls`); the rest of the package allows untyped defs.
- Domain logic must not hard-code a single UI — go through the abstract `App` interface.
- Reuse the shared helpers (downloads, running programs, registry, package offers,
  version comparison): see "Use these instead of writing your own" in
  [ARCHITECTURE.md](ARCHITECTURE.md).
- Comments say why, not what changed: history belongs in commit messages.
- Mark technical debt with `FIXME:`.

## Pointers

- [ARCHITECTURE.md](ARCHITECTURE.md) — module map, UI pattern, control flow.
- [CONTRIBUTING.md](CONTRIBUTING.md) — full dev setup and Docker build.
- [tests/manual-testing.md](tests/manual-testing.md) — manual testing guide.
- [.github/workflows/](.github/workflows/) — CI; `run-tests.yml` runs unit tests on PRs.
