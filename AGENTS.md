# Repository Guidelines

This guide helps contributors and automation agents work effectively in this repo.

## Project Structure & Module Organization
- Source: `kagebunshin/` (core agent, automation, tools, communication, cli, config, utils)
- Tests: `tests/` mirrors package modules (e.g., `tests/core/test_agent.py`)
- Docs & assets: `docs/`, `examples/`, `dist/`, `runs/`
- Entrypoint: `kagebunshin.__main__:main` (CLI `kagebunshin`)

## Build, Test, and Development Commands
```bash
# Setup (Python 3.13+, uv)
uv sync --all-extras && uv run playwright install chromium

# Run CLI
uv run -m kagebunshin "Your task"

# Tests
uv run pytest -q         # run all tests
uv run pytest -v tests/core/test_agent.py  # module

# Quality
uv run black . && uv run isort .
uv run flake8 kagebunshin/ && uv run mypy kagebunshin/

# Build distribution
uv build  # (hatchling backend)
```

## Coding Style & Naming Conventions
- Python 3.13, 4-space indent, max line length 88 (Black).
- Use type hints; mypy is configured to disallow untyped defs.
- Naming: modules/functions `snake_case`, classes `CamelCase`, constants `UPPER_CASE`.
- Keep public APIs documented with concise docstrings; prefer small, composable functions.

## Testing Guidelines
- Framework: `pytest` with asyncio enabled (`pytest.ini`).
- Place tests under `tests/` mirroring package paths; files `test_*.py`, tests `test_*`.
- Write focused unit tests; use fixtures in `tests/conftest.py` when shared setup is needed.
- Run locally with `uv run pytest`; ensure new code is covered by tests where practical.

## Commit & Pull Request Guidelines
- Use Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
- Commits should be small and scoped; include context in the body when needed.
- PRs must: describe the change, link issues, note breaking changes, include tests, and update docs/examples if applicable.
- Before opening a PR: run formatting, linting, type checks, and tests (see commands above).

## Security & Configuration Tips
- Keep secrets out of VCS; use `.env` locally. Required keys typically include `OPENAI_API_KEY` (and optionally `ANTHROPIC_API_KEY`).
- Install Playwright browsers (`uv run playwright install chromium`) before running browser code.
- Prefer `uv` workflows; do not commit `.venv/` or generated artifacts in `dist/`.

