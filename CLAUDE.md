# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`tbctl` is a CLI for ThingsBoard. It uses a Python client generated from `openapi-4.3.0.1PE.json` and exposes `tbctl auth`, `tbctl config`, `tbctl ota`, `tbctl device`, `tbctl alias`, `tbctl telemetry`, and `tbctl attributes` subcommands.

The client lives in `generated/tb_client/`, built by `./generate.sh`.

## Commands

```sh
uv sync                 # install deps into venv
uv run tbctl            # run the CLI during development
uv tool install .       # install the CLI globally
tbctl --install-completion  # install completion for the current shell (zsh -> ~/.zfunc/_tbctl)
tbctl completion <shell>    # print the completion script for a named shell

uv run pytest                                        # run all tests
uv run pytest tests/test_ota.py::test_delete        # run a single test
uv run pytest --cov=tbctl --cov-report=term-missing  # with coverage

pre-commit run --all-files              # lint + format check
uv run ruff check tbctl/ tests/         # lint
uv run ruff format --check tbctl/ tests/  # format check
```

## Architecture

- `tbctl/cli.py` - root Typer app and `completion <shell>`
- `tbctl/config.py` - the config file (`-c FILE` > `TBCTL_CONFIG` > `~/.config/tbctl/config.toml`) with one `[contexts.<name>]` per server, the only source of its url and user (`auth login` asks for and writes a missing context or user after a successful login) (url, user, default, aliases, protected_attributes), plus a top-level protected_attributes for every context (`attributes set`/`delete` refuse the union); no permission check, it holds no secret; edited with `tomlkit` so comments stay; resolves the `Context` (`--context` > `TBCTL_CONTEXT` > `default = true` > only one) once per command via `active(ctx)`, quietly for completion via `try_active(ctx)`; `Context.key` is `<name>@<url>`; warns about any other key
- `tbctl/state.py` - what tbctl writes itself, per `Context.key`: auth, refresh_expires, customer_id, token on fallback, in `~/.local/state/tbctl/state.toml` with mode 0600, plus the renewal lock files
- `tbctl/credentials.py` - the credential: `TBCTL_TOKEN` (an API key), else the Secret Service via `keyring` (service `tbctl`, user = `Context.key`), else `token` in the state file; the secret is a JSON JWT pair (`auth = "jwt"`) or an API key (`auth = "api-key"`); a secret without `auth` counts as not logged in
- `tbctl/session.py` - login (username/password -> JWT pair), renewal via the refresh token under a per-context lock when the access token has under a minute left (`ensure_fresh`, called by `_configuration`, returns token and header prefix), logout
- `tbctl/aliases.py` - local per-context device aliases (`[contexts.<name>.aliases]` in the config file), resolved by `resolve_device_id` and offered as shell completion on every `<device>` argument
- `tbctl/keycache.py` - telemetry and attribute keys seen per device, and the device name -> UUID cache filled by `resolve_device_id` and `device list`, in `~/.cache/tbctl/<user>@<host>/keys.json` (user from the config; nothing cached without one), so `--keys` and `<device>` completion stay local and a known name needs no lookup
- `tbctl/commands/` - one module per subcommand group (`auth.py`, `config_cmd.py`, `ota.py`, `device.py`, `alias.py`, `telemetry.py`, `attributes.py`)
- `tbctl/commands/_client.py` - shared helpers for the telemetry/attributes commands: authenticated client builders, `resolve_device_id` (UUID or name lookup), `handle_api_error`, and `parse_response`
- `tbctl/commands/_format.py` - timestamp (UTC or `--local`), value and cell-width formatting shared by the telemetry/attributes tables
- `generated/tb_client/` - Python client generated from `openapi-4.3.0.1PE.json` by `./generate.sh` (gitignored; run it once before installing or testing)

The generated client returns telemetry and attribute endpoints as a Python `repr` string (single-quoted, not valid JSON). `parse_response` coerces these via `json.loads` then `ast.literal_eval`; wrap every such response in it.

Auth uses `X-Authorization: Bearer <jwt>` or `X-Authorization: ApiKey <key>` via the generated client's `Configuration.api_key`.

## Tooling

- Licence: Apache 2.0
- `pyproject.toml` only - no `setup.py` or `requirements.txt`
- `uv.lock` for reproducible installs - commit this file
- `ruff` for formatting, import sorting, and linting
- LSP: `python-lsp-server` + `python-lsp-ruff` as dev dependencies
- Tests: `pytest` + `pytest-cov`
- Pre-commit hooks enforce formatting and linting before every commit
