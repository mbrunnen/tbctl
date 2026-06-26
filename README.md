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

tb device list
tb device list --search sensor --type default --sort-by createdTime --sort-order DESC
tb device list --json
tb device get <device>
tb device create sensor-1 --profile default --label Lobby
tb device update sensor-1 --label "Main hall" --profile thermostat
tb device delete sensor-1 --yes
tb device assign sensor-1 --customer <customer-uuid>

tb telemetry keys <device>
tb telemetry latest <device> --keys temperature,humidity
tb telemetry history <device> --keys temperature --last 24h
tb telemetry history <device> --keys temperature --start 2026-06-01 --end 2026-06-25
tb telemetry history <device> --keys temperature --last 7d --plot

tb attributes get <device>
tb attributes get <device> --scope SERVER_SCOPE --keys fwVersion
```

`<device>` accepts a device UUID or a device name. Name resolution needs an API
token with tenant device-read permission; otherwise pass the UUID directly.

## Development

```sh
uv sync
uv run tb
uv run pytest
pre-commit run --all-files
```
