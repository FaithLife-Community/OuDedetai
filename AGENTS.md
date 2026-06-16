# AGENTS.md

Guidance for AI coding agents working in this repository. For full human-facing
setup instructions see [CONTRIBUTING.md](CONTRIBUTING.md); for the user-facing
overview see [README.md](README.md).

## Project overview

OuDedetai installs and maintains FaithLife's Logos/Verbum Bible software on Linux
via Wine. It is a FaithLife Community project (MIT licensed). The shipped artifact
is a PyInstaller binary that detects the user's OS and package manager, installs
Wine and its dependencies, and creates desktop shortcuts.

## Setup

- Requires **Python 3.12+** built with Tcl/Tk.
- `./scripts/ensure-python.sh` — builds/installs Python 3.12 if needed.
- `./scripts/ensure-venv.sh` — creates and configures the virtual environment.
- With a 3.12 venv active: `pip install .[dev]` (includes `mypy` and `ruff`).

## Common commands

- **Run:** `python -m ou_dedetai.main --help`
- **GUI mode:** `DIALOG=tk ./oudedetai` (default is TUI)
- **Tests:** `./scripts/run-tests.sh`
- **Lint:** `ruff check`
- **Type check:** `mypy ou_dedetai`
- **Build binary:** `./scripts/build-binary.sh x86_64`

## Testing

- **Framework:** stdlib `unittest` only — no pytest.
- **Location:** [tests/](tests/) — `test_<module>.py` per covered domain module
  (currently `backup`, `constants`, `network`, `utils`); add one when you touch a
  module that lacks coverage. `tests/integration.py` holds end-to-end checks.
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
- Mark technical debt with `FIXME:`.

## Pointers

- [ARCHITECTURE.md](ARCHITECTURE.md) — module map, UI pattern, control flow.
- [CONTRIBUTING.md](CONTRIBUTING.md) — full dev setup and Docker build.
- [tests/manual-testing.md](tests/manual-testing.md) — manual testing guide.
- [.github/workflows/](.github/workflows/) — CI; `run-tests.yml` runs unit tests on PRs.
