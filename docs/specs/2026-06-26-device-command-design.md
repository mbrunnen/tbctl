# Device command group design

## Goal

Add a `tb device` command group covering create, read (get and list), update,
and delete of ThingsBoard devices, mirroring the conventions already used by
`tb ota` and `tb attributes`.

## Module and registration

- New module `tb/commands/device.py` exposing `app = typer.Typer(...)`.
- Registered in `tb/cli.py` via `app.add_typer(device.app, name="device")`.
- Reuses existing helpers from `tb/commands/_client.py`: `device_api`,
  `resolve_device_id`, `handle_api_error`.

## Generated client surface

`DeviceControllerApi` provides:

- `get_tenant_devices(page_size, page, type, text_search, sort_property, sort_order)` -> `PageDataDevice`
- `get_device_by_id(device_id)` -> `Device`
- `get_tenant_device(device_name)` -> `Device` (used by `resolve_device_id`)
- `save_device(device)` -> `Device` (upsert: no `id` creates, `id` updates)
- `delete_device(device_id)`

`DeviceProfileControllerApi` provides:

- `get_default_device_profile_info()` -> `DeviceProfileInfo`
- `get_device_profile_infos(page_size, page, text_search)` -> `PageDataDeviceProfileInfo`

The `Device` model marks `deviceProfileId` as required, so `create` must always
resolve a profile UUID before calling `save_device`.

## Commands

### `device list`

Paginated table of tenant devices.

- Flags: `--page-size` (default 20), `--search/-s` (name substring),
  `--type/-t` (device profile name), `--sort-by`, `--sort-order`, `--json/-j`.
- Calls `get_tenant_devices(page_size=..., page=0, ...)`.
- Table columns: ID, Name, Type, Label, Created (UTC).
- Empty result prints `[]` (JSON) or `No devices found.`.
- `--json` dumps `model_dump(by_alias=True, exclude_none=True)` per device,
  matching `ota list`.

### `device get <id|name>`

- Resolve argument via `resolve_device_id`.
- Fetch with `get_device_by_id`.
- Print `to_dict()` as indented JSON.

### `device create <name>`

- Flags: `--label`, `--profile` (profile name, default `"default"`).
- Resolve the profile name to a UUID (see Profile resolution).
- Build a `Device(name=..., label=..., device_profile_id=DeviceProfileId(...))`
  with no `id`, call `save_device`.
- Print the new device UUID.

### `device update <id|name>`

Read-modify-write to avoid clobbering untouched fields.

- Resolve and fetch the existing `Device`.
- Overlay only the flags that were provided: `--name`, `--label`, `--profile`.
  `--profile` is resolved to a UUID and replaces `device_profile_id`.
- Preserve `id`, `tenantId`, `version`, `deviceData`, `additionalInfo`.
- Call `save_device` with the merged device.
- Print confirmation.

### `device delete <id|name>`

- Resolve argument.
- `--yes/-y` skips the `typer.confirm` prompt (mirrors `ota delete`).
- Call `delete_device`.
- Print `Deleted <id>`.

## Profile resolution

New helper in `device.py`, `resolve_profile_id(profile, name) -> str`:

- If `name == "default"`: call `get_default_device_profile_info()`, return
  `info.id.id`.
- Otherwise: call `get_device_profile_infos(page_size=..., text_search=name)`
  and select the entry whose name matches `name` exactly (case-insensitive).
  - Zero exact matches: error `Device profile '<name>' not found.` and exit 1.
  - Multiple exact matches: error listing the ambiguity and exit 1.

## Error handling

- All API calls wrapped via `handle_api_error`.
- The 403 case for name lookup is already handled inside `resolve_device_id`.

## Testing

`tests/test_device.py`, mocking `DeviceControllerApi` and
`DeviceProfileControllerApi`, in the style of `tests/test_ota.py`:

- `create`: success (profile resolved, `save_device` called without `id`);
  profile not found; ambiguous profile.
- `update`: only provided flags change; `id`/`version` preserved.
- `delete`: confirm prompt path and `--yes` path.
- `get`: resolves and prints JSON.
- `list`: table output, `--json` output, empty result.

## Out of scope

- Device credentials management.
- Customer assignment / entity groups.
- Bulk operations and JSON-body input (flags-only for now).
