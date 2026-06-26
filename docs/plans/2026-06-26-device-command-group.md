# Device Command Group Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `tb device` command group with create, get, list, update, and delete subcommands.

**Architecture:** A new `tb/commands/device.py` Typer app registered in `tb/cli.py`, reusing the shared helpers in `tb/commands/_client.py` (`device_api`, `resolve_device_id`, `handle_api_error`) plus a new `device_profile_api` helper. Device profile names are resolved to UUIDs before `save_device`, because the generated `Device` model requires `deviceProfileId`.

**Tech Stack:** Python, Typer, Rich, pytest, the generated `tb_client` (`DeviceControllerApi`, `DeviceProfileControllerApi`).

## Global Constraints

- Licence: Apache 2.0; no inline comments restating code.
- `ruff` formatting and linting must pass (`uv run ruff check tb/ tests/`, `uv run ruff format --check tb/ tests/`).
- Files end with a trailing newline.
- Tests use `typer.testing.CliRunner` and mock the API layer, in the style of `tests/test_ota.py`.
- The config profile (`ctx.obj["profile"]`) and the device-profile name (`--profile`) are distinct; never conflate them. Use `cfg_profile` for the config profile inside command bodies.

---

### Task 1: Add `device_profile_api` helper

**Files:**
- Modify: `tb/commands/_client.py`
- Test: `tests/test_device.py` (created here)

**Interfaces:**
- Produces: `device_profile_api(profile: str) -> DeviceProfileControllerApi`

- [ ] **Step 1: Write the failing test**

Create `tests/test_device.py`:

```python
import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from tb.cli import app

runner = CliRunner()

DEVICE_UUID = "11111111-1111-1111-1111-111111111111"
PROFILE_UUID = "22222222-2222-2222-2222-222222222222"


def test_device_profile_api_builds_controller():
    from tb.commands import _client

    with patch.object(_client, "_configuration", return_value=MagicMock()):
        api = _client.device_profile_api("default")

    from tb_client.api.device_profile_controller_api import DeviceProfileControllerApi

    assert isinstance(api, DeviceProfileControllerApi)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_device.py::test_device_profile_api_builds_controller -v`
Expected: FAIL with `AttributeError: module 'tb.commands._client' has no attribute 'device_profile_api'`

- [ ] **Step 3: Add the helper**

In `tb/commands/_client.py`, after `device_api`:

```python
def device_profile_api(profile: str):
    from tb_client.api.device_profile_controller_api import DeviceProfileControllerApi

    return DeviceProfileControllerApi(_configuration(profile))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_device.py::test_device_profile_api_builds_controller -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tb/commands/_client.py tests/test_device.py
git commit -m "Add device_profile_api client helper"
```

---

### Task 2: Scaffold `device` module with `list`

**Files:**
- Create: `tb/commands/device.py`
- Modify: `tb/cli.py`
- Test: `tests/test_device.py`

**Interfaces:**
- Consumes: `device_api`, `handle_api_error` from `tb/commands/_client.py`
- Produces: `app` (Typer), `device list` command

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_device.py`:

```python
def _mock_device(
    device_id=DEVICE_UUID, name="sensor-1", dev_type="default", label="Lobby", created=0
):
    dev = MagicMock()
    dev.id.id = device_id
    dev.name = name
    dev.type = dev_type
    dev.label = label
    dev.created_time = created
    return dev


def test_list():
    mock_api = MagicMock()
    mock_api.get_tenant_devices.return_value.data = [_mock_device()]
    mock_api.get_tenant_devices.return_value.total_elements = 1

    with patch("tb.commands.device.device_api", return_value=mock_api):
        result = runner.invoke(app, ["device", "list"])

    assert result.exit_code == 0
    assert "sensor-1" in result.output
    mock_api.get_tenant_devices.assert_called_once_with(
        page_size=20,
        page=0,
        type=None,
        text_search=None,
        sort_property=None,
        sort_order=None,
    )


def test_list_empty():
    mock_api = MagicMock()
    mock_api.get_tenant_devices.return_value.data = []

    with patch("tb.commands.device.device_api", return_value=mock_api):
        result = runner.invoke(app, ["device", "list"])

    assert result.exit_code == 0
    assert "No devices found" in result.output


def test_list_json():
    dev = _mock_device()
    dev.model_dump.return_value = {"name": "sensor-1"}
    mock_api = MagicMock()
    mock_api.get_tenant_devices.return_value.data = [dev]
    mock_api.get_tenant_devices.return_value.total_elements = 1

    with patch("tb.commands.device.device_api", return_value=mock_api):
        result = runner.invoke(app, ["device", "list", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == [{"name": "sensor-1"}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_device.py -k list -v`
Expected: FAIL (no `device` command registered)

- [ ] **Step 3: Create the module**

Create `tb/commands/device.py`:

```python
import json
from datetime import datetime, timezone

import typer

from tb.commands._client import (
    device_api,
    device_profile_api,
    handle_api_error,
    resolve_device_id,
)

app = typer.Typer(no_args_is_help=True, help="Manage devices.")


def _fmt_ts(ms) -> str:
    if not ms:
        return "-"
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


@app.command("list")
def list_devices(
    ctx: typer.Context,
    page_size: int = typer.Option(20, "--page-size", help="Devices per page."),
    text_search: str = typer.Option(None, "--search", "-s", help="Substring filter on name."),
    type: str = typer.Option(None, "--type", "-t", help="Filter by device profile name."),
    sort_property: str = typer.Option(None, "--sort-by", help="Property to sort by."),
    sort_order: str = typer.Option(None, "--sort-order", help="ASC or DESC."),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON."),
):
    api = device_api(ctx.obj["profile"])
    try:
        result = api.get_tenant_devices(
            page_size=page_size,
            page=0,
            type=type,
            text_search=text_search,
            sort_property=sort_property,
            sort_order=sort_order,
        )
    except Exception as e:
        handle_api_error(e)

    if not result.data:
        typer.echo("[]" if output_json else "No devices found.")
        return

    if output_json:
        typer.echo(
            json.dumps(
                [d.model_dump(by_alias=True, exclude_none=True) for d in result.data],
                indent=2,
                default=str,
            )
        )
        return

    from rich.console import Console
    from rich.table import Table

    table = Table(show_header=True, header_style="bold")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("Label")
    table.add_column("Created (UTC)")
    for d in result.data:
        device_id = str(d.id.id) if d.id is not None else ""
        table.add_row(
            device_id,
            d.name or "",
            d.type or "",
            d.label or "",
            _fmt_ts(getattr(d, "created_time", None)),
        )
    console = Console()
    console.print(table)
    console.print(f"Showing {len(result.data)} of {result.total_elements} devices")
```

- [ ] **Step 4: Register in the root app**

In `tb/cli.py`, add `device` to the import and register it:

```python
from tb.commands import attributes, config_cmd, device, ota, telemetry

app = typer.Typer(no_args_is_help=True)
app.add_typer(config_cmd.app, name="config")
app.add_typer(ota.app, name="ota")
app.add_typer(telemetry.app, name="telemetry")
app.add_typer(attributes.app, name="attributes")
app.add_typer(device.app, name="device")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_device.py -k list -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add tb/commands/device.py tb/cli.py tests/test_device.py
git commit -m "Add device list command"
```

---

### Task 3: Add `device get`

**Files:**
- Modify: `tb/commands/device.py`
- Test: `tests/test_device.py`

**Interfaces:**
- Consumes: `resolve_device_id`, `device_api`
- Produces: `device get` command

- [ ] **Step 1: Write the failing test**

Append to `tests/test_device.py`:

```python
def test_get():
    mock_api = MagicMock()
    mock_api.get_device_by_id.return_value.to_dict.return_value = {"name": "sensor-1"}

    with patch("tb.commands.device.device_api", return_value=mock_api):
        result = runner.invoke(app, ["device", "get", DEVICE_UUID])

    assert result.exit_code == 0
    assert json.loads(result.output) == {"name": "sensor-1"}
    mock_api.get_device_by_id.assert_called_once_with(device_id=DEVICE_UUID)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_device.py::test_get -v`
Expected: FAIL (no `get` command)

- [ ] **Step 3: Add the command**

Append to `tb/commands/device.py`:

```python
@app.command("get")
def get_device(ctx: typer.Context, device: str = typer.Argument(help="Device UUID or name.")):
    cfg_profile = ctx.obj["profile"]
    device_id = resolve_device_id(cfg_profile, device)
    api = device_api(cfg_profile)
    try:
        dev = api.get_device_by_id(device_id=device_id)
    except Exception as e:
        handle_api_error(e)
    typer.echo(json.dumps(dev.to_dict(), indent=2, default=str))
```

Note: passing a UUID argument means `resolve_device_id` returns it without an API call, so the test needs no profile-lookup mock.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_device.py::test_get -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tb/commands/device.py tests/test_device.py
git commit -m "Add device get command"
```

---

### Task 4: Add profile resolution and `device create`

**Files:**
- Modify: `tb/commands/device.py`
- Test: `tests/test_device.py`

**Interfaces:**
- Consumes: `device_profile_api`, `device_api`, `handle_api_error`
- Produces: `resolve_profile_id(profile: str, name: str) -> str`, `device create` command

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_device.py`:

```python
def _mock_profile_info(name="custom", profile_id=PROFILE_UUID):
    info = MagicMock()
    info.name = name
    info.id.id = profile_id
    return info


def test_create_default_profile():
    profile_api = MagicMock()
    profile_api.get_default_device_profile_info.return_value.id.id = PROFILE_UUID
    device_api_mock = MagicMock()
    device_api_mock.save_device.return_value.id.id = DEVICE_UUID

    with (
        patch("tb.commands.device.device_profile_api", return_value=profile_api),
        patch("tb.commands.device.device_api", return_value=device_api_mock),
    ):
        result = runner.invoke(app, ["device", "create", "sensor-1"])

    assert result.exit_code == 0
    assert DEVICE_UUID in result.output
    sent = device_api_mock.save_device.call_args.kwargs["device"]
    assert sent.name == "sensor-1"
    assert sent.id is None
    assert str(sent.device_profile_id.id) == PROFILE_UUID


def test_create_named_profile():
    profile_api = MagicMock()
    profile_api.get_device_profile_infos.return_value.data = [_mock_profile_info(name="custom")]
    device_api_mock = MagicMock()
    device_api_mock.save_device.return_value.id.id = DEVICE_UUID

    with (
        patch("tb.commands.device.device_profile_api", return_value=profile_api),
        patch("tb.commands.device.device_api", return_value=device_api_mock),
    ):
        result = runner.invoke(app, ["device", "create", "sensor-1", "--profile", "custom"])

    assert result.exit_code == 0
    sent = device_api_mock.save_device.call_args.kwargs["device"]
    assert str(sent.device_profile_id.id) == PROFILE_UUID


def test_create_profile_not_found():
    profile_api = MagicMock()
    profile_api.get_device_profile_infos.return_value.data = []

    with patch("tb.commands.device.device_profile_api", return_value=profile_api):
        result = runner.invoke(app, ["device", "create", "sensor-1", "--profile", "ghost"])

    assert result.exit_code == 1
    assert "not found" in result.output


def test_create_profile_ambiguous():
    profile_api = MagicMock()
    profile_api.get_device_profile_infos.return_value.data = [
        _mock_profile_info(name="dup", profile_id=PROFILE_UUID),
        _mock_profile_info(name="dup", profile_id=DEVICE_UUID),
    ]

    with patch("tb.commands.device.device_profile_api", return_value=profile_api):
        result = runner.invoke(app, ["device", "create", "sensor-1", "--profile", "dup"])

    assert result.exit_code == 1
    assert "ambiguous" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_device.py -k create -v`
Expected: FAIL (no `create` command)

- [ ] **Step 3: Add resolver and command**

Append to `tb/commands/device.py`:

```python
def resolve_profile_id(profile: str, name: str) -> str:
    api = device_profile_api(profile)
    try:
        if name == "default":
            info = api.get_default_device_profile_info()
            return str(info.id.id)
        result = api.get_device_profile_infos(page_size=100, text_search=name)
    except Exception as e:
        handle_api_error(e)

    matches = [p for p in result.data if (p.name or "").lower() == name.lower()]
    if not matches:
        typer.echo(f"Device profile '{name}' not found.", err=True)
        raise typer.Exit(1)
    if len(matches) > 1:
        typer.echo(f"Device profile '{name}' is ambiguous ({len(matches)} matches).", err=True)
        raise typer.Exit(1)
    return str(matches[0].id.id)


@app.command("create")
def create_device(
    ctx: typer.Context,
    name: str = typer.Argument(help="Unique device name."),
    label: str = typer.Option(None, "--label", help="Display label."),
    profile: str = typer.Option("default", "--profile", help="Device profile name."),
):
    from tb_client.models.device import Device
    from tb_client.models.device_profile_id import DeviceProfileId

    cfg_profile = ctx.obj["profile"]
    profile_id = resolve_profile_id(cfg_profile, profile)
    device = Device(
        name=name,
        label=label,
        device_profile_id=DeviceProfileId(id=profile_id, entity_type="DEVICE_PROFILE"),
    )
    api = device_api(cfg_profile)
    try:
        result = api.save_device(device=device)
    except Exception as e:
        handle_api_error(e)
    typer.echo(f"Created {result.id.id}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_device.py -k create -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add tb/commands/device.py tests/test_device.py
git commit -m "Add device create command with profile-name resolution"
```

---

### Task 5: Add `device update`

**Files:**
- Modify: `tb/commands/device.py`
- Test: `tests/test_device.py`

**Interfaces:**
- Consumes: `resolve_device_id`, `resolve_profile_id`, `device_api`
- Produces: `device update` command

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_device.py`:

```python
def test_update_label_only():
    existing = MagicMock()
    existing.name = "sensor-1"
    existing.label = "old"
    mock_api = MagicMock()
    mock_api.get_device_by_id.return_value = existing

    with patch("tb.commands.device.device_api", return_value=mock_api):
        result = runner.invoke(app, ["device", "update", DEVICE_UUID, "--label", "new"])

    assert result.exit_code == 0
    sent = mock_api.save_device.call_args.kwargs["device"]
    assert sent.label == "new"
    assert sent.name == "sensor-1"


def test_update_profile_resolves():
    existing = MagicMock()
    mock_api = MagicMock()
    mock_api.get_device_by_id.return_value = existing
    profile_api = MagicMock()
    profile_api.get_device_profile_infos.return_value.data = [_mock_profile_info(name="custom")]

    with (
        patch("tb.commands.device.device_api", return_value=mock_api),
        patch("tb.commands.device.device_profile_api", return_value=profile_api),
    ):
        result = runner.invoke(
            app, ["device", "update", DEVICE_UUID, "--profile", "custom"]
        )

    assert result.exit_code == 0
    sent = mock_api.save_device.call_args.kwargs["device"]
    assert str(sent.device_profile_id.id) == PROFILE_UUID
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_device.py -k update -v`
Expected: FAIL (no `update` command)

- [ ] **Step 3: Add the command**

Append to `tb/commands/device.py`:

```python
@app.command("update")
def update_device(
    ctx: typer.Context,
    device: str = typer.Argument(help="Device UUID or name."),
    name: str = typer.Option(None, "--name", help="New device name."),
    label: str = typer.Option(None, "--label", help="New display label."),
    profile: str = typer.Option(None, "--profile", help="New device profile name."),
):
    from tb_client.models.device_profile_id import DeviceProfileId

    cfg_profile = ctx.obj["profile"]
    device_id = resolve_device_id(cfg_profile, device)
    api = device_api(cfg_profile)
    try:
        existing = api.get_device_by_id(device_id=device_id)
    except Exception as e:
        handle_api_error(e)

    if name is not None:
        existing.name = name
    if label is not None:
        existing.label = label
    if profile is not None:
        existing.device_profile_id = DeviceProfileId(
            id=resolve_profile_id(cfg_profile, profile), entity_type="DEVICE_PROFILE"
        )

    try:
        api.save_device(device=existing)
    except Exception as e:
        handle_api_error(e)
    typer.echo(f"Updated {device_id}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_device.py -k update -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add tb/commands/device.py tests/test_device.py
git commit -m "Add device update command"
```

---

### Task 6: Add `device delete`

**Files:**
- Modify: `tb/commands/device.py`
- Test: `tests/test_device.py`

**Interfaces:**
- Consumes: `resolve_device_id`, `device_api`
- Produces: `device delete` command

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_device.py`:

```python
def test_delete_with_yes():
    mock_api = MagicMock()

    with patch("tb.commands.device.device_api", return_value=mock_api):
        result = runner.invoke(app, ["device", "delete", DEVICE_UUID, "--yes"])

    assert result.exit_code == 0
    mock_api.delete_device.assert_called_once_with(device_id=DEVICE_UUID)


def test_delete_confirm_aborts():
    mock_api = MagicMock()

    with patch("tb.commands.device.device_api", return_value=mock_api):
        result = runner.invoke(app, ["device", "delete", DEVICE_UUID], input="n\n")

    assert result.exit_code != 0
    mock_api.delete_device.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_device.py -k delete -v`
Expected: FAIL (no `delete` command)

- [ ] **Step 3: Add the command**

Append to `tb/commands/device.py`:

```python
@app.command("delete")
def delete_device(
    ctx: typer.Context,
    device: str = typer.Argument(help="Device UUID or name."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
):
    cfg_profile = ctx.obj["profile"]
    device_id = resolve_device_id(cfg_profile, device)
    if not yes:
        typer.confirm(f"Delete device {device_id}?", abort=True)
    api = device_api(cfg_profile)
    try:
        api.delete_device(device_id=device_id)
    except Exception as e:
        handle_api_error(e)
    typer.echo(f"Deleted {device_id}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_device.py -k delete -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add tb/commands/device.py tests/test_device.py
git commit -m "Add device delete command"
```

---

### Task 7: Full verification and docs

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run the full suite with linting**

Run:
```bash
uv run pytest
uv run ruff check tb/ tests/
uv run ruff format --check tb/ tests/
```
Expected: all tests pass, no lint or format errors.

- [ ] **Step 2: Add a Device section to the README**

In `README.md`, under the existing command documentation, add a `tb device` section documenting `list`, `get`, `create`, `update`, and `delete` with one example each, matching the style of the existing sections. Example block:

```markdown
## Devices

```sh
tb device list --search sensor          # paginated table of devices
tb device get <uuid|name>               # device as JSON
tb device create sensor-1 --profile default --label Lobby
tb device update sensor-1 --label "Main hall"
tb device delete sensor-1 --yes
```
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Document tb device commands in README"
```

---

## Self-Review Notes

- Spec coverage: list (Task 2), get (Task 3), create + profile resolution (Task 4), update (Task 5), delete (Task 6), tests throughout, README (Task 7). All spec sections mapped.
- `resolve_profile_id` signature is consistent across Tasks 4 and 5.
- `cfg_profile` naming convention applied in every command body that resolves a device or profile.
- Out-of-scope items (credentials, customer assignment, JSON-body input) are intentionally absent.
