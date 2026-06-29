# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`tb` is a CLI for ThingsBoard OTA package management. It uses a Python client generated from `openapi-4.3.0.1PE.json` and exposes `tb config` and `tb ota` subcommands.

The client lives in `generated/tb_client/`, built by `./generate.sh`.

## Commands

```sh
uv sync                 # install deps into venv
uv run tb               # run the CLI during development
pipx install .          # install the CLI globally
tb --install-completion zsh  # install zsh completion to ~/.zfunc/_tb

uv run pytest                                     # run all tests
uv run pytest tests/test_ota.py::test_delete      # run a single test
uv run pytest --cov=tb --cov-report=term-missing  # with coverage

pre-commit run --all-files             # lint + format check
uv run ruff check tb/ tests/           # lint
uv run ruff format --check tb/ tests/  # format check
```

## Architecture

- `tb/cli.py` - root Typer app
- `tb/config.py` - reads/writes `~/.config/tb/config.toml` (url + token)
- `tb/commands/` - one module per subcommand group (`config_cmd.py`, `ota.py`, `telemetry.py`, `attributes.py`)
- `tb/commands/_client.py` - shared helpers for the telemetry/attributes commands: authenticated client builders, `resolve_device_id` (UUID or name lookup), `handle_api_error`, and `parse_response`
- `generated/tb_client/` - Python client generated from `openapi-4.3.0.1PE.json` by `./generate.sh` (gitignored; run it once before installing or testing)

The generated client returns telemetry and attribute endpoints as a Python `repr` string (single-quoted, not valid JSON). `parse_response` coerces these via `json.loads` then `ast.literal_eval`; wrap every such response in it.

Auth uses `X-Authorization: ApiKey <token>` via the generated client's `Configuration.api_key`.

## Tooling

- Licence: Apache 2.0
- `pyproject.toml` only - no `setup.py` or `requirements.txt`
- `uv.lock` for reproducible installs - commit this file
- `ruff` for formatting, import sorting, and linting
- LSP: `python-lsp-server` + `python-lsp-ruff` as dev dependencies
- Tests: `pytest` + `pytest-cov`
- Pre-commit hooks enforce formatting and linting before every commit
