# tb

CLI for ThingsBoard OTA package management.

## Installation

```sh
pipx install .
tb --install-completion zsh
exec zsh
```

## Update

```sh
pipx reinstall tb
tb --install-completion zsh
exec zsh
```

## Configuration

```sh
tb config set-url https://thingsboard.example.com
tb config set-token <api-token>
tb config show
```

Multiple profiles are supported via `--profile <name>` (default: `default`).

## Usage

```sh
tb ota list
tb ota list --search firmware --type FIRMWARE --sort-by createdTime --sort-order DESC
tb ota list --device-profile <uuid> --type FIRMWARE
tb ota list --json

tb ota get <uuid>
tb ota delete <uuid>
```

## Development

```sh
uv sync
uv run tb
uv run pytest
pre-commit run --all-files
```
