# tbctl

CLI for ThingsBoard OTA package management.

## Installation

```sh
pipx install \
  --index-url https://test.pypi.org/simple/ \
  --pip-args="--extra-index-url https://pypi.org/simple/" \
  tbctl
tbctl --install-completion
exec zsh
```

`tbctl` is published to TestPyPI; the extra index lets pipx resolve the runtime
dependencies from PyPI.

## Update

```sh
pipx reinstall tbctl
tbctl --install-completion
exec zsh
```

## Configuration

The quickest way to get started is the interactive wizard, which prompts for the
URL and token and verifies them against the server before saving:

```sh
tbctl config init
```

The individual commands are also available:

```sh
tbctl config set-url https://thingsboard.example.com
tbctl config set-token <api-token>
tbctl config show
```

Multiple config profiles are supported via `--config <name>` / `-c` (default: `default`).

## Usage

```sh
tbctl ota list
tbctl ota list --search firmware --type FIRMWARE --sort-by createdTime --sort-order DESC
tbctl ota list --device-profile <uuid> --type FIRMWARE
tbctl ota list --json

tbctl ota get <uuid>
tbctl ota delete <uuid>

tbctl ota upload firmware.bin --title app-fw --version 1.4.0 --device-profile sensor-v2
tbctl ota upload firmware.bin --title app-sw --version 1.4.0 --type SOFTWARE --device-profile sensor-v2
tbctl ota upload --url http://host/fw.bin --title app-fw --version 1.4.0 --device-profile sensor-v2

tbctl ota download <uuid>                                   # by package id
tbctl ota download --device-profile sensor-v2               # profile's assigned firmware
tbctl ota download --device-profile sensor-v2 --version 1.4.0
tbctl ota download --device thermostat-01                   # device's firmware (falls back to its profile)
tbctl ota download --device thermostat-01 --version 1.4.0
tbctl ota download --name app-fw --latest                   # newest package with this title
tbctl ota download --name app-fw --version 1.4.0 --type SOFTWARE
tbctl ota download --name app-fw -o ./out.bin --force       # custom path, overwrite if present

tbctl ota assign app-fw thermostat-01                       # assign latest by title, to a device
tbctl ota assign app-fw thermostat-01 --version 1.4.0 --type SOFTWARE
tbctl ota assign <package-uuid> <device-uuid>
tbctl ota unassign thermostat-01                            # clear the device's FIRMWARE assignment
tbctl ota unassign thermostat-01 --type SOFTWARE

tbctl device list
tbctl device list --search sensor --type default --sort-by createdTime --sort-order DESC
tbctl device list --customer <customer-uuid> --token   # devices of a customer, with access tokens
tbctl device list --json
tbctl device get <device>
tbctl device create sensor-1 --profile default --label Lobby
tbctl device update sensor-1 --label "Main hall" --profile thermostat
tbctl device delete sensor-1 --yes
tbctl device assign sensor-1 --customer <customer-uuid>

tbctl telemetry keys <device>
tbctl telemetry latest <device> --keys temperature,humidity
tbctl telemetry history <device> --keys temperature --last 24h
tbctl telemetry history <device> --keys temperature --start 2026-06-01 --end 2026-06-25
tbctl telemetry history <device> --keys temperature --last 7d --plot

tbctl attributes get <device>
tbctl attributes get <device> --scope SERVER_SCOPE --keys fwVersion
```

`<device>` accepts a device UUID or a device name. Name resolution needs an API
token with tenant device-read permission; otherwise pass the UUID directly.

`tbctl ota upload` creates a package from exactly one source: a local file
argument or `--url` for an externally hosted package. `--title`, `--version`,
and `--device-profile` (name or UUID) are required; `--type` defaults to
`FIRMWARE`. For file uploads the checksum is computed locally
(`--checksum-algorithm`, default `SHA256`) and sent alongside the data.

`tbctl ota download` takes exactly one selector (a package id, `--device-profile`,
`--device`, or `--name`). For a profile or device, the assigned package is used
unless `--version` is given; for `--name`, the newest version is used unless
`--version` is given. `--type` defaults to `FIRMWARE` (`--type SOFTWARE` for
software). Without `-o/--output` the file is saved under the package's own file
name in the current directory, and an existing file is only overwritten with
`--force`.

`tbctl ota assign` takes a package id or title and a device. `--type` defaults
to `FIRMWARE`; with a title, the newest version is used unless `--version` is
given. `tbctl ota unassign` clears the device's `--type` assignment (default
`FIRMWARE`).

## Development

```sh
uv sync
uv run tbctl
uv run pytest
pre-commit run --all-files
```
