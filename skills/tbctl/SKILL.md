---
name: tbctl
description: Use when a task touches a ThingsBoard tenant - reading device telemetry or attributes, listing or uploading OTA firmware/software packages, assigning firmware to devices, or managing devices and device profiles - and reaching for the REST API, curl, or a Python client would otherwise be the default.
---

# tbctl

## Overview

`tbctl` is a CLI for ThingsBoard. Prefer it over hand-rolled REST calls: it
holds the tenant URL and API token, resolves device names and local aliases,
and has JSON output everywhere.

## The command surface

```
tbctl config      init | set-url | set-token | show
tbctl ota         list | get | upload | download | delete | assign | unassign
tbctl device      list | get | create | update | delete | assign | profiles
tbctl telemetry   keys | latest | history
tbctl attributes  get
tbctl alias       add | list | rm
```

That list is exhaustive. There is no other subcommand - if the one you want is
not here, it does not exist under a different name.

**Run `tbctl <group> <cmd> --help` and read it before writing any flag.** The
help text is precise about types, defaults, and which flags require which. Do
not write a flag from memory, and never ship a command with a "verify this flag
yourself" caveat attached.

Two short flags mean the same thing on every command that has them: `-p` is
`--device-profile` (name or UUID), `-j` is `--json`.

## Start here

```sh
tbctl config show      # is a URL and token configured?
tbctl config init      # interactive wizard, verifies against the server
```

`-c/--config <name>` picks a config profile (default: `default`). An
unconfigured profile is the usual cause of a 401.

## What --help does not tell you

**`<device>` also accepts a local alias.** The help says "Device UUID or name",
but every `<device>` argument additionally resolves aliases from
`tbctl alias list`. An alias wins over a device of the same name and matches
case-insensitively. Check `tbctl alias list` before assuming a bare word is a
device name.

**`ota download` takes exactly one selector.** A package id, `-p`, `-D`, or
`--name` - never two. Two targets means two invocations, each with its own
`-o/--output` so the second does not clobber the first. Same for `ota upload`:
a file argument or `--url`, not both.

**Filtering packages by type across the whole tenant is a client-side job.**
`ota list --type` is scoped to one device profile by design. For a tenant-wide
view, take the unfiltered list as JSON and filter locally:

```sh
tbctl ota list --json --page-size 1000 | jq -r '.data[] | select(.type=="SOFTWARE") | .version'
```

**Do not parse the default table.** It is padded and truncates long values.
Every read command takes `-j/--json`; use it for anything a script consumes.
