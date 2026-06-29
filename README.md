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

tb ota download <uuid>                                   # by package id
tb ota download --device-profile sensor-v2               # profile's assigned firmware
tb ota download --device-profile sensor-v2 --version 1.4.0
tb ota download --device thermostat-01                   # device's firmware (falls back to its profile)
tb ota download --device thermostat-01 --version 1.4.0
tb ota download --name app-fw --latest                   # newest package with this title
tb ota download --name app-fw --version 1.4.0 --type SOFTWARE
tb ota download --name app-fw -o ./out.bin --force       # custom path, overwrite if present

tb device list
tb device list --search sensor --type default --sort-by createdTime --sort-order DESC
tb device list --customer <customer-uuid> --token   # devices of a customer, with access tokens
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

`tb ota download` takes exactly one selector (a package id, `--device-profile`,
`--device`, or `--name`). For a profile or device, the assigned package is used
unless `--version` is given; for `--name`, the newest version is used unless
`--version` is given. `--type` defaults to `FIRMWARE` (`--type SOFTWARE` for
software). Without `-o/--output` the file is saved under the package's own file
name in the current directory, and an existing file is only overwritten with
`--force`.

## Development

```sh
uv sync
uv run tb
uv run pytest
pre-commit run --all-files
```
