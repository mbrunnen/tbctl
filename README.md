# tbctl

CLI for ThingsBoard: OTA packages, devices, telemetry, attributes, and local
device aliases.

## Installation

```sh
uv tool install tbctl
tbctl --install-completion
exec zsh
```

`--install-completion` detects the current shell. To generate the script for a
named shell instead, e.g. for packaging, use `tbctl completion`:

```sh
tbctl completion bash > ~/.local/share/bash-completion/completions/tbctl
```

### Testing pre-releases

Release candidates are published to TestPyPI. Install one with the extra index
so uv can resolve the runtime dependencies from PyPI:

```sh
uv tool install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  tbctl
```

### From a local checkout

To install the working tree instead of the published package, point `uv tool
install` at the path (a bare `uv tool install tbctl` fails because the package
is not on the public registry):

```sh
./generate.sh            # build the generated client (gitignored, bundled into the wheel)
uv tool install .        # install the current checkout as a uv tool
tbctl --install-completion
exec zsh
```

## Update

```sh
uv tool upgrade tbctl
tbctl --install-completion
exec zsh
```

For a local checkout, `uv tool upgrade` does not apply; reinstall instead.
Because the version does not change between builds, `--refresh` is needed to
bypass the cached wheel:

```sh
uv tool install . --reinstall --refresh
```

## Configuration

After installing, log in:

```sh
tbctl auth login
```

```
ThingsBoard URL: https://thingsboard.example.com
Username: me@example.com
Password:
Logged in to https://thingsboard.example.com as me@example.com; session valid until ...
Added context 'thingsboard.example.com' to ~/.config/tbctl/config.toml.
```

The first login creates `~/.config/tbctl/config.toml` with a context named
after the server's host, which becomes the default. All servers and logins live
in this one file, one context per section; it is the only source of each
context's URL and user, and you may edit it by hand:

```toml
protected_attributes = ["iccid", "imei"]

[contexts.preprod]
url = "https://preprod.example.com"
user = "me@example.com"
default = true

[contexts.preprod.aliases]
ruedi = { name = "OX1-Y2HUZR" }

[contexts.PROD]
url = "https://prod.example.com"
user = "me@example.com"
```

Later logins ask only for the password. A context that is missing from the
file is asked for and added, and a context without `user` gets one, both only
after the login succeeds:

```sh
tbctl auth login                    # the default context
tbctl --context PROD auth login     # adds PROD if missing: asks URL and username
tbctl auth login --url https://tb.example.com --user me@example.com  # no URL or username prompt
```

`--url` and `--user` replace the prompts; if the file already has another
value, login fails.

`auth login` stores the session the server returns (a JWT access token and its
refresh token), never the password. Any tbctl command renews the access token
when it is about to expire. Once the refresh token has expired (after 7 days
by default, set by the server), log in again. While a session is valid,
`auth login` renews it and asks for no password; to log in anew, for example as
another user, run `auth logout` first. Two-factor authentication is not
supported. To change a URL or user, edit the file. tbctl edits it only for
`alias add`, `alias delete` and a login that adds a context or user, and keeps
your comments and layout.

To use an API key you created in ThingsBoard instead, store it with
`--api-key`; such a context needs no `user`. tbctl reads the key from a hidden
prompt, or from stdin when piped, and uses it as it is:

```sh
tbctl auth login --api-key
```

```sh
tbctl auth status            # who is logged in, how, and until when
tbctl auth status --json
tbctl auth refresh           # renew the session now
tbctl auth logout            # end the session and forget the credential
tbctl config show            # file, context and its settings
tbctl config contexts        # all contexts, the default marked
```

tbctl picks the config file and the context in this order:

| | First | Then | Then | Last |
|---|---|---|---|---|
| File | `-c/--config FILE` | `TBCTL_CONFIG` | `~/.config/tbctl/config.toml` | |
| Context | `--context NAME` | `TBCTL_CONTEXT` | the context with `default = true` | the only context |

With several contexts and no default, tbctl stops and asks for `--context`.
A config file can live anywhere, for example in a repository: it holds no
secret. tbctl keeps what it writes itself (the kind of login, the session's
expiry, the customer) in `~/.local/state/tbctl/state.toml`, keyed
by `<context>@<url>`. The secret is kept in the Secret Service (KWallet, GNOME
Keyring) under the same key, so two config files with the same context name
and URL share one login. Where no Secret Service is available, as in a Docker
container or a devcontainer, or with `tbctl auth login --insecure-storage`,
the secret goes into the state file instead, and tbctl warns when it does so.
tbctl refuses a state file that others can read, and names the `chmod` to
run. The config file holds no secret, so its permissions do not matter.

When you log in as a customer user, tbctl remembers your customer, so
`device list` and device names use that customer's devices instead of the
tenant-wide endpoints a customer user may not call.

`TBCTL_TOKEN` overrides the stored login for every context and is used as an
API key:

```sh
export TBCTL_TOKEN=<api-key>
```

### Upgrading from 0.x

Version 1 reads no `~/.config/tbctl/<profile>.toml` file. Copy the `url`,
`aliases` and `protected_attributes` of each old profile into a
`[contexts.<profile>]` section of `config.toml`, add your `user`, mark one
context with `default = true`, and log in again for each context. Replace `-c <profile>` with
`--context <profile>` in scripts.

## Usage

```sh
tbctl ota list
tbctl ota list --search firmware --type FIRMWARE --sort-by createdTime --sort-order DESC
tbctl ota list -v 1.4.0                                   # filter by version (client-side)
tbctl ota list --search app-fw -v 1.4.0                   # narrow by title, then version
tbctl ota list --device-profile sensor-v2                  # name or UUID; both types when --type omitted
tbctl ota list --device-profile sensor-v2 --type FIRMWARE
tbctl ota list --json

tbctl ota get <uuid>
tbctl ota get app-fw --version 1.4.0 --json
tbctl ota delete app-fw --latest

tbctl ota upload firmware.bin --title app-fw --version 1.4.0 --device-profile sensor-v2
tbctl ota upload firmware.bin --title app-sw --version 1.4.0 --type SOFTWARE --device-profile sensor-v2
tbctl ota upload --external-url http://host/fw.bin --title app-fw --version 1.4.0 --device-profile sensor-v2

tbctl ota download <uuid>                                   # by package id
tbctl ota download --device-profile sensor-v2               # profile's assigned firmware
tbctl ota download --device-profile sensor-v2 --version 1.4.0
tbctl ota download --device thermostat-01                   # device's firmware (falls back to its profile)
tbctl ota download --device thermostat-01 --version 1.4.0
tbctl ota download app-fw --latest                          # newest package with this title
tbctl ota download app-fw --version 1.4.0 --type SOFTWARE
tbctl ota download app-fw --latest -o ./out.bin --force     # custom path, overwrite if present

tbctl ota assign app-fw thermostat-01 --latest              # assign the newest version to a device
tbctl ota assign app-fw thermostat-01 --version 1.4.0 --type SOFTWARE
tbctl ota assign <package-uuid> <device-uuid>
tbctl ota unassign thermostat-01                            # clear the device's FIRMWARE assignment
tbctl ota unassign thermostat-01 --type SOFTWARE
tbctl ota devices app-fw --latest                           # devices that run the newest app-fw
tbctl ota devices app-fw --version 1.4.0 --type FIRMWARE --device-profile thermostat

tbctl device list
tbctl device list --search sensor --device-profile default --sort-by createdTime --sort-order DESC
tbctl device list --customer <customer-uuid> --token   # devices of a customer, with access tokens
tbctl device list --json
tbctl device profiles                                  # list device profiles
tbctl device profiles --search sensor --json
tbctl device get <device>                              # includes firmware and software
tbctl device get <device> --json
tbctl device get <device> --token                      # include the access token
tbctl device create sensor-1 --device-profile default --label Lobby
tbctl device update sensor-1 --label "Main hall" --device-profile thermostat
tbctl device delete sensor-1 --yes
tbctl device assign sensor-1 --customer <customer-uuid>

tbctl alias add ruedi OX1-Y2HUZR       # remember a device under a free-text name
tbctl alias add horst OX1-1T6570 --id <device-uuid>   # skips the name lookup
tbctl alias list
tbctl alias list --json
tbctl alias delete horst
tbctl telemetry latest ruedi --keys temperature   # aliases work as <device>

tbctl telemetry keys <device>
tbctl telemetry latest <device> --keys temperature,humidity
tbctl telemetry latest <device> --local                  # local time instead of UTC
tbctl telemetry history <device>                         # all keys, last 24h
tbctl telemetry history <device> --keys temperature --last 7d
tbctl telemetry history <device> --keys temperature --last 20   # the 20 newest points
tbctl telemetry history <device> --keys temperature --start 2026-06-01 --end 2026-06-25
tbctl telemetry history <device> --keys temperature --last 7d --agg avg --interval 1h
tbctl telemetry history <device> --keys temperature --last 7d --plot

tbctl attributes get <device>                            # shared scope
tbctl attributes get <device> --scope server --keys fwVersion
tbctl attributes keys <device> --scope server
tbctl attributes set <device> mode=eco interval=300      # values are JSON, else text
tbctl attributes delete <device> mode --yes
```

`telemetry history` shows one table with a column per key; values longer
than 40 characters are cut, and `--json` keeps them whole. `--keys`
completes the keys tbctl has already seen for that device; run
`tbctl telemetry keys <device>` once to fill the cache. The cache is kept per
login in `~/.cache/tbctl/<user>@<host>/`, so contexts with the same `user` and
host share it; a context without `user` caches nothing.

`attributes set` and `attributes delete` write the shared scope unless
`--scope server` is given; client attributes belong to the device and cannot
be written. List keys that must never change, and both commands refuse them
before anything is sent. A top-level list applies to every context; a list in
a context adds to it:

```toml
protected_attributes = ["iccid", "imei"]

[contexts.PROD]
url = "https://prod.example.com"
protected_attributes = ["serial_number"]
```

`<device>` accepts a device UUID, a device name, or a local alias. Name
resolution needs tenant device-read permission, or a customer login (which
searches that customer's devices); otherwise pass the UUID directly.

`-p/--device-profile` means the same thing on every command that takes one
(`ota list|upload|download`, `device list|create|update`) and accepts a device
profile name or a UUID. Every read command prints a table by default and JSON
with `-j/--json`.

`tbctl alias` stores free-text names for devices in the active context
(`[contexts.<name>.aliases]` in the config file, one entry per alias with a
required `name` and an optional `id`); they never leave your machine. An alias
resolves wherever `<device>` is accepted, takes precedence over a device of the
same name, and matches case-insensitively. `--id` stores the device UUID
alongside the name, which is what makes the alias work with a token that lacks
tenant device-read permission: resolving then needs no name lookup. `alias add`
replaces the whole entry, so repeating it without `--id` drops a stored UUID.
Shell completion suggests the aliases of the active context, and `tbctl device
list` gains an `Alias` column while the context has any, matched by device name
or UUID.

`tbctl ota upload` creates a package from exactly one source: a local file
argument or `--external-url` for an externally hosted package. `--title`, `--version`,
and `--device-profile` (name or UUID) are required; `--type` defaults to
`FIRMWARE`. For file uploads the checksum is computed locally
(`--checksum-algorithm`, default `SHA256`) and sent alongside the data.

`tbctl ota list --search` maps to ThingsBoard's server-side text search, which
matches the package title only. Use `-v/--version` for a client-side,
case-insensitive substring filter on the version; when given, all pages are
fetched and filtered locally, and it combines with `--search`. The listing shows
each package's device profile; `--device-profile` accepts a name or UUID, and
without `--type` it lists both `FIRMWARE` and `SOFTWARE` packages (`--type` alone
still requires `--device-profile`).

`<package>` means the same thing in `ota get|delete|devices|assign|download`: a
package UUID, or a title (ignoring case) with `--version` or `--latest`. A title
alone is refused, so no command acts on a version you did not name. A title
that exists as both `FIRMWARE` and `SOFTWARE` needs `--type`, and a title and
version that match several packages need the UUID.

`tbctl ota download` takes exactly one selector (a `<package>`,
`--device-profile`, or `--device`). For a profile or device, the assigned
package is used unless `--version` is given. `--type` defaults to `FIRMWARE`
(`--type SOFTWARE` for software). Without `-o/--output` the file is saved under the package's own file
name in the current directory, and an existing file is only overwritten with
`--force`.

`tbctl ota assign` takes a `<package>` and a device. `--type` defaults to
`FIRMWARE`. `tbctl ota unassign` clears the device's `--type` assignment (default
`FIRMWARE`).

`tbctl ota devices` lists the devices that run one `<package>`. A device without its own
assignment runs the package of its device profile; such rows show `profile` as
the source. `tbctl device get` shows the same resolution for one device, marked
`(inherited from profile)`.

## Claude Code skill

`skills/tbctl/` is a [Claude Code](https://claude.ai/code) skill that teaches an
agent how to drive this CLI: the command surface, which selectors are mutually
exclusive, and why `--json` matters for anything that gets parsed.

Install it for your user by linking it into the personal skills directory, so a
`git pull` keeps it current:

```sh
mkdir -p ~/.claude/skills
ln -s "$PWD/skills/tbctl" ~/.claude/skills/tbctl
```

Codex, Copilot CLI, and Gemini CLI read `~/.agents/skills/` instead:

```sh
mkdir -p ~/.agents/skills
ln -s "$PWD/skills/tbctl" ~/.agents/skills/tbctl
```

To scope it to a single project rather than your user, link it into that
project's `.claude/skills/` instead. Either way the agent loads the skill on
its own once a task mentions ThingsBoard, OTA packages, or telemetry; no slash
command needed.

## Development

```sh
./generate.sh   # build the client first, so the editable install can see it
uv sync
uv run tbctl
uv run pytest
pre-commit run --all-files
```

The editable install only sees `tb_client` if it exists at install time. After
regenerating the client, refresh the editable path:

```sh
uv pip install -e . --force-reinstall
```
