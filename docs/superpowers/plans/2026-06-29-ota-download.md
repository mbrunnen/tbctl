# OTA download command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `tb ota download` to fetch an OTA package binary to disk, selectable by UUID, device profile, device, or package title (current/latest or a specific `--version`).

**Architecture:** A single `download` command in `tb/commands/ota.py`. Selectors resolve to one `OtaPackageInfo` (typed OTA client works fine), whose bytes are fetched via `download_ota_package`. Device and device-profile entity reads must bypass the generated models (the `Device` model fails to deserialize `deviceData` and the device-profile controller cannot be imported), so they go through raw JSON via the device client — the same helpers `device.py` already uses, lifted into `_client.py` to share.

**Tech Stack:** Python, Typer, pytest, the generated `tb_client`.

## Global Constraints

- Licence: Apache 2.0; no new runtime dependencies.
- No inline rationale comments; self-documenting names (per repo + user rules).
- British English in any user-facing text; files end with `\n`.
- `--type` default is `FIRMWARE`; `--type SOFTWARE` switches.
- Default output is the package's own `file_name` in CWD; never overwrite without `--force`.
- Tests mock the API objects in `tb.commands.ota`'s namespace and never hit the network, mirroring `tests/test_ota.py`.
- Run lint/format before every commit: `uv run ruff check tb/ tests/ && uv run ruff format tb/ tests/`.

## File Structure

- `tb/commands/_client.py` — gains shared `raw_json`, `raw_get`, `resolve_profile_id` (moved from `device.py`).
- `tb/commands/device.py` — imports those three from `_client.py` instead of defining them.
- `tb/commands/ota.py` — gains the `download` command and its private resolvers.
- `tests/test_ota.py` — gains the download tests.
- `tests/test_device.py` — unchanged; must stay green after the move.

---

### Task 1: Lift raw-JSON device-client helpers into `_client.py`

Behaviour-preserving extraction so `ota.py` can reuse `raw_get`/`resolve_profile_id` without depending on a sibling command module. Verified by the existing `test_device.py` suite.

**Hard guardrail:** Touch ONLY `tb/commands/_client.py`, `tb/commands/device.py`, and `tests/test_device.py`. Do NOT modify, regenerate, or delete anything under `tb_client/` or `generated/`, and do NOT run `generate.sh` — the generated client is managed separately and is already working.

**Why test_device.py changes:** `test_device.py` patches `tb.commands.device._raw_get` and `tb.commands.device.device_api` inside the four tests that exercise the *real* `resolve_profile_id`. Once `resolve_profile_id`, `raw_get`, and `raw_json` live in `_client.py`, `resolve_profile_id` calls `_client.device_api`/`_client.raw_get`, so those four tests must patch the `_client` namespace instead. The other patches (`device.device_api` for list/get/etc., and `device.resolve_profile_id` for create/update success) stay as-is because `device.py` still calls `device_api` directly and still exposes the imported `resolve_profile_id` name.

**Files:**
- Modify: `tb/commands/_client.py`
- Modify: `tb/commands/device.py`
- Modify: `tests/test_device.py` (retarget 8 patch strings in 4 functions; see Step 2b)

**Interfaces:**
- Produces (in `tb.commands._client`):
  - `raw_json(response) -> dict | list` — raises `ApiException` on status >= 400, else `json.loads(response.data)`.
  - `raw_get(api, resource_path: str, query: list | None = None) -> dict | list` — authenticated GET via the device client's `api_client`, returns parsed JSON.
  - `resolve_profile_id(profile: str, name: str) -> str` — device-profile name → UUID (`"default"` special-cased), exits 1 on no/ambiguous match.

- [ ] **Step 1: Add the three helpers to `_client.py`**

Append to `tb/commands/_client.py` (after `resolve_device_id`):

```python
def raw_json(response):
    """Parse a raw client response body, bypassing the generated models.

    The ``Device`` model cannot deserialise ThingsBoard's ``deviceData``: its
    transport configuration is an undiscriminated ``oneOf`` that matches several
    schemas at once. Reading the response as plain JSON sidesteps this. The
    no-preload client path does not raise on error status, so check it here.
    """
    if response.status >= 400:
        from tb_client.exceptions import ApiException

        raise ApiException(http_resp=response)
    return json.loads(response.data)


def raw_get(api, resource_path, query=None):
    """GET a path via the device client and return parsed JSON.

    The generated device and device-profile controllers cannot be used for these
    reads (an undeserialisable ``oneOf`` and a circular import respectively), so
    reuse the importable device client's HTTP machinery instead.
    """
    ac = api.api_client
    request = ac.param_serialize(
        method="GET",
        resource_path=resource_path,
        query_params=query or [],
        header_params={"Accept": "application/json"},
        auth_settings=["API key form"],
    )
    response = ac.call_api(*request)
    response.read()
    return raw_json(response)


def resolve_profile_id(profile: str, name: str) -> str:
    api = device_api(profile)
    try:
        if name == "default":
            return raw_get(api, "/api/deviceProfileInfo/default")["id"]["id"]
        page = raw_get(
            api,
            "/api/deviceProfileInfos",
            [("pageSize", 100), ("page", 0), ("textSearch", name)],
        )
    except Exception as e:
        handle_api_error(e)

    matches = [p for p in page.get("data", []) if (p.get("name") or "").lower() == name.lower()]
    if not matches:
        typer.echo(f"Device profile '{name}' not found.", err=True)
        raise typer.Exit(1)
    if len(matches) > 1:
        typer.echo(f"Device profile '{name}' is ambiguous ({len(matches)} matches).", err=True)
        raise typer.Exit(1)
    return matches[0]["id"]["id"]
```

- [ ] **Step 2: Update `device.py` to import them**

In `tb/commands/device.py`, extend the existing `from tb.commands._client import (...)` block to include `raw_get`, `raw_json`, `resolve_profile_id`. Then delete the local `_raw_json`, `_raw_get`, and `resolve_profile_id` definitions, and replace internal calls `_raw_json(` → `raw_json(` and `_raw_get(` → `raw_get(` throughout `device.py`.

- [ ] **Step 2b: Retarget the affected patches in `tests/test_device.py`**

Only inside these four functions — `test_resolve_profile_default`, `test_resolve_profile_named_exact_match`, `test_create_profile_not_found`, `test_create_profile_ambiguous` — change the two patch targets:

```python
# before
patch("tb.commands.device.device_api", return_value=MagicMock()),
patch("tb.commands.device._raw_get", return_value=...),
# after
patch("tb.commands._client.device_api", return_value=MagicMock()),
patch("tb.commands._client.raw_get", return_value=...),
```

Leave every other `patch("tb.commands.device.device_api", ...)` and `patch("tb.commands.device.resolve_profile_id", ...)` in the file unchanged.

- [ ] **Step 3: Run the device suite to verify no regression**

Run: `uv run pytest tests/test_device.py -q`
Expected: PASS (all existing device tests green — the patch target `tb.commands.device.resolve_profile_id` still exists as an imported name).

- [ ] **Step 4: Run the full suite + lint**

Run: `uv run pytest -q && uv run ruff check tb/ tests/ && uv run ruff format tb/ tests/`
Expected: 66 passed; ruff clean.

- [ ] **Step 5: Commit**

```bash
git add tb/commands/_client.py tb/commands/device.py tests/test_device.py
git commit -m "Extract raw-JSON device-client helpers into _client"
```

---

### Task 2: `download` command frame — by-id, output, and validation

Delivers a working `tb ota download <uuid>` with full output handling and all cross-selector validation. Later tasks wire the remaining selectors.

**Files:**
- Modify: `tb/commands/ota.py`
- Test: `tests/test_ota.py`

**Interfaces:**
- Consumes: `tb.commands._client.{device_api, resolve_device_id, resolve_profile_id, raw_get, handle_api_error}`; `OtaPackageControllerApi.{get_ota_package_info_by_id, download_ota_package, get_ota_packages, get_ota_packages1}`.
- Produces:
  - command `download` on the `ota` Typer app.
  - `_resolve_package_info(cfg_profile, *, package_id, device_profile, device, name, version, latest, pkg_type) -> OtaPackageInfo` — returns the selected package info; in this task only the `package_id` branch is implemented, other selectors raise `typer.Exit` with a "not implemented" stub replaced in Tasks 3–5.
  - `_write_package(info, data, output, force)` — writes bytes to `output` or `info.file_name` (fallback `f"{info.title}-{info.version}.bin"`) in CWD; refuses overwrite without `force`.

- [ ] **Step 1: Write the failing tests (by-id happy path, output default, force, validation)**

Add to `tests/test_ota.py`:

```python
from pathlib import Path


def _mock_info(pkg_id="abc-123", title="Firmware", version="1.0",
               pkg_type="FIRMWARE", file_name="fw_1.0.bin"):
    info = MagicMock()
    info.id.id = pkg_id
    info.title = title
    info.version = version
    info.type = pkg_type
    info.file_name = file_name
    return info


def test_download_by_id(tmp_path):
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.return_value = _mock_info()
    mock_api.download_ota_package.return_value = b"BINARY"
    out = tmp_path / "out.bin"

    with patch("tb.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "download", "abc-123", "-o", str(out)])

    assert result.exit_code == 0, result.output
    mock_api.download_ota_package.assert_called_once_with(ota_package_id="abc-123")
    assert out.read_bytes() == b"BINARY"


def test_download_default_filename(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.return_value = _mock_info(file_name="fw_1.0.bin")
    mock_api.download_ota_package.return_value = b"BINARY"

    with patch("tb.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "download", "abc-123"])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "fw_1.0.bin").read_bytes() == b"BINARY"


def test_download_fallback_filename(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.return_value = _mock_info(file_name=None)
    mock_api.download_ota_package.return_value = b"BINARY"

    with patch("tb.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "download", "abc-123"])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "Firmware-1.0.bin").read_bytes() == b"BINARY"


def test_download_refuses_overwrite(tmp_path):
    out = tmp_path / "out.bin"
    out.write_bytes(b"OLD")
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.return_value = _mock_info()
    mock_api.download_ota_package.return_value = b"NEW"

    with patch("tb.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "download", "abc-123", "-o", str(out)])

    assert result.exit_code != 0
    assert "exists" in result.output
    assert out.read_bytes() == b"OLD"


def test_download_force_overwrite(tmp_path):
    out = tmp_path / "out.bin"
    out.write_bytes(b"OLD")
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.return_value = _mock_info()
    mock_api.download_ota_package.return_value = b"NEW"

    with patch("tb.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "download", "abc-123", "-o", str(out), "--force"])

    assert result.exit_code == 0, result.output
    assert out.read_bytes() == b"NEW"


def test_download_no_selector():
    with patch("tb.commands.ota._get_api", return_value=MagicMock()):
        result = runner.invoke(app, ["ota", "download"])
    assert result.exit_code != 0
    assert "Provide exactly one" in result.output


def test_download_multiple_selectors():
    with patch("tb.commands.ota._get_api", return_value=MagicMock()):
        result = runner.invoke(app, ["ota", "download", "abc-123", "--name", "fw"])
    assert result.exit_code != 0
    assert "exactly one" in result.output


def test_download_version_and_latest():
    with patch("tb.commands.ota._get_api", return_value=MagicMock()):
        result = runner.invoke(
            app, ["ota", "download", "--name", "fw", "--version", "1.0", "--latest"]
        )
    assert result.exit_code != 0
    assert "--version" in result.output and "--latest" in result.output


def test_download_latest_without_name():
    with patch("tb.commands.ota._get_api", return_value=MagicMock()):
        result = runner.invoke(app, ["ota", "download", "abc-123", "--latest"])
    assert result.exit_code != 0
    assert "--latest" in result.output


def test_download_version_with_id():
    with patch("tb.commands.ota._get_api", return_value=MagicMock()):
        result = runner.invoke(app, ["ota", "download", "abc-123", "--version", "1.0"])
    assert result.exit_code != 0
    assert "--version" in result.output
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_ota.py -k download -q`
Expected: FAIL (no such command `download`).

- [ ] **Step 3: Implement the command frame, validation, by-id, and output**

In `tb/commands/ota.py`, extend the top imports:

```python
from pathlib import Path

from tb.commands._client import (
    device_api,
    handle_api_error,
    raw_get,
    resolve_device_id,
    resolve_profile_id,
)
```

Add (after `delete_package`):

```python
def _validate_selectors(package_id, device_profile, device, name, version, latest):
    selectors = [package_id, device_profile, device, name]
    if sum(bool(s) for s in selectors) != 1:
        typer.echo(
            "Provide exactly one selector: a package id, --device-profile, --device, or --name.",
            err=True,
        )
        raise typer.Exit(1)
    if version and latest:
        typer.echo("--version and --latest are mutually exclusive.", err=True)
        raise typer.Exit(1)
    if latest and not name:
        typer.echo("--latest is only valid with --name.", err=True)
        raise typer.Exit(1)
    if version and package_id:
        typer.echo("--version cannot be combined with a package id.", err=True)
        raise typer.Exit(1)


def _resolve_package_info(
    cfg_profile, *, package_id, device_profile, device, name, version, latest, pkg_type
):
    api = _get_api(cfg_profile)
    if package_id:
        try:
            return api.get_ota_package_info_by_id(ota_package_id=package_id)
        except Exception as e:
            _handle_api_error(e)
    typer.echo("Selector not implemented yet.", err=True)
    raise typer.Exit(1)


def _write_package(info, data, output, force):
    if output:
        target = Path(output)
    else:
        target = Path(info.file_name or f"{info.title}-{info.version}.bin")
    if target.exists() and not force:
        typer.echo(f"{target} exists; pass --force to overwrite or set --output.", err=True)
        raise typer.Exit(1)
    target.write_bytes(data)
    typer.echo(f"Wrote {target} ({_format_size(len(data))})")


@app.command("download")
def download_package(
    ctx: typer.Context,
    package_id: str = typer.Argument(None, help="OTA package UUID."),
    device_profile: str = typer.Option(
        None, "--device-profile", "-p", help="Resolve via device profile name or UUID."
    ),
    device: str = typer.Option(
        None, "--device", "-D", help="Resolve via device name or UUID."
    ),
    name: str = typer.Option(None, "--name", "-n", help="Resolve by OTA package title."),
    version: str = typer.Option(None, "--version", "-v", help="Specific package version."),
    latest: bool = typer.Option(False, "--latest", help="Newest version (with --name)."),
    type: str = typer.Option("FIRMWARE", "--type", "-t", help="FIRMWARE or SOFTWARE."),
    output: str = typer.Option(None, "--output", "-o", help="Output file path."),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing output."),
):
    pkg_type = type.upper()
    if pkg_type not in ("FIRMWARE", "SOFTWARE"):
        typer.echo("--type must be FIRMWARE or SOFTWARE.", err=True)
        raise typer.Exit(1)
    _validate_selectors(package_id, device_profile, device, name, version, latest)

    cfg_profile = ctx.obj["profile"]
    info = _resolve_package_info(
        cfg_profile,
        package_id=package_id,
        device_profile=device_profile,
        device=device,
        name=name,
        version=version,
        latest=latest,
        pkg_type=pkg_type,
    )
    api = _get_api(cfg_profile)
    try:
        data = api.download_ota_package(ota_package_id=info.id.id)
    except Exception as e:
        _handle_api_error(e)
    _write_package(info, data, output, force)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_ota.py -k download -q`
Expected: PASS (10 download tests).

- [ ] **Step 5: Run full suite + lint, then commit**

Run: `uv run pytest -q && uv run ruff check tb/ tests/ && uv run ruff format tb/ tests/`
Expected: all green.

```bash
git add tb/commands/ota.py tests/test_ota.py
git commit -m "Add tb ota download with by-id selector and output handling"
```

---

### Task 3: Resolve by `--name` (title)

**Files:**
- Modify: `tb/commands/ota.py`
- Test: `tests/test_ota.py`

**Interfaces:**
- Consumes: `OtaPackageControllerApi.get_ota_packages(page_size, page, text_search, sort_property, sort_order)` -> page with `.data` list of `OtaPackageInfo`.
- Produces: `_select_from_candidates(candidates, version, label) -> OtaPackageInfo` — filters by `version` or picks newest `created_time`; exits 1 with a clear message when empty.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_ota.py` (extend `_mock_info` usage with `created_time`):

```python
def test_download_by_name_latest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    old = _mock_info(pkg_id="old", version="1.0", file_name="fw_1.0.bin")
    old.created_time = 100
    new = _mock_info(pkg_id="new", version="2.0", file_name="fw_2.0.bin")
    new.created_time = 200
    mock_api = MagicMock()
    mock_api.get_ota_packages.return_value.data = [old, new]
    mock_api.download_ota_package.return_value = b"NEW"

    with patch("tb.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "download", "--name", "Firmware"])

    assert result.exit_code == 0, result.output
    mock_api.download_ota_package.assert_called_once_with(ota_package_id="new")


def test_download_by_name_version(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    old = _mock_info(pkg_id="old", version="1.0", file_name="fw_1.0.bin")
    old.created_time = 100
    new = _mock_info(pkg_id="new", version="2.0", file_name="fw_2.0.bin")
    new.created_time = 200
    mock_api = MagicMock()
    mock_api.get_ota_packages.return_value.data = [old, new]
    mock_api.download_ota_package.return_value = b"OLD"

    with patch("tb.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(
            app, ["ota", "download", "--name", "Firmware", "--version", "1.0"]
        )

    assert result.exit_code == 0, result.output
    mock_api.download_ota_package.assert_called_once_with(ota_package_id="old")


def test_download_by_name_type_filter(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fw = _mock_info(pkg_id="fw", pkg_type="FIRMWARE", file_name="fw.bin")
    fw.created_time = 100
    sw = _mock_info(pkg_id="sw", pkg_type="SOFTWARE", file_name="sw.bin")
    sw.created_time = 200
    mock_api = MagicMock()
    mock_api.get_ota_packages.return_value.data = [fw, sw]
    mock_api.download_ota_package.return_value = b"SW"

    with patch("tb.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(
            app, ["ota", "download", "--name", "Firmware", "--type", "SOFTWARE"]
        )

    assert result.exit_code == 0, result.output
    mock_api.download_ota_package.assert_called_once_with(ota_package_id="sw")


def test_download_by_name_not_found():
    mock_api = MagicMock()
    mock_api.get_ota_packages.return_value.data = []

    with patch("tb.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "download", "--name", "Nope"])

    assert result.exit_code != 0
    assert "Nope" in result.output


def test_download_by_name_version_not_found():
    info = _mock_info(version="1.0")
    info.created_time = 100
    mock_api = MagicMock()
    mock_api.get_ota_packages.return_value.data = [info]

    with patch("tb.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(
            app, ["ota", "download", "--name", "Firmware", "--version", "9.9"]
        )

    assert result.exit_code != 0
    assert "9.9" in result.output
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_ota.py -k "by_name" -q`
Expected: FAIL ("Selector not implemented yet.").

- [ ] **Step 3: Implement the `--name` branch**

In `tb/commands/ota.py`, add the selector helper near `_resolve_package_info`:

```python
def _select_from_candidates(candidates, version, label):
    if version:
        candidates = [c for c in candidates if c.version == version]
        if not candidates:
            typer.echo(f"No package matching {label} at version '{version}'.", err=True)
            raise typer.Exit(1)
    if not candidates:
        typer.echo(f"No package matching {label}.", err=True)
        raise typer.Exit(1)
    return max(candidates, key=lambda c: c.created_time or 0)
```

In `_resolve_package_info`, replace the trailing stub (`typer.echo("Selector not implemented yet."...)`) with the `name` branch (keep the stub `raise` as the final fallthrough for now):

```python
    if name:
        try:
            page = api.get_ota_packages(
                page_size=100, page=0, text_search=name,
                sort_property=None, sort_order=None,
            )
        except Exception as e:
            _handle_api_error(e)
        candidates = [
            p for p in page.data
            if (p.title or "") == name and (p.type or "") == pkg_type
        ]
        return _select_from_candidates(candidates, version, f"name '{name}'")
    typer.echo("Selector not implemented yet.", err=True)
    raise typer.Exit(1)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_ota.py -k "by_name" -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Run full suite + lint, then commit**

Run: `uv run pytest -q && uv run ruff check tb/ tests/ && uv run ruff format tb/ tests/`

```bash
git add tb/commands/ota.py tests/test_ota.py
git commit -m "Resolve tb ota download by package title"
```

---

### Task 4: Resolve by `--device-profile`

**Files:**
- Modify: `tb/commands/ota.py`
- Test: `tests/test_ota.py`

**Interfaces:**
- Consumes: `_client.resolve_profile_id`, `_client.device_api`, `_client.raw_get`; `OtaPackageControllerApi.get_ota_packages1(device_profile_id, type, page_size, page, text_search, sort_property, sort_order)`.
- Produces: `_assigned_ota_id(entity, pkg_type, label) -> str` — reads `firmwareId`/`softwareId` from a raw entity dict; exits 1 if unset.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_ota.py`. Note `_UUID_RE` in `_client` decides UUID vs name; use a real-looking UUID for the pass-through case and a plain name otherwise.

```python
PROFILE_UUID = "11111111-1111-1111-1111-111111111111"


def test_download_by_profile_current_firmware(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.return_value = _mock_info(pkg_id="fw-id")
    mock_api.download_ota_package.return_value = b"FW"
    profile = {"firmwareId": {"id": "fw-id"}, "softwareId": {"id": "sw-id"}}

    with (
        patch("tb.commands.ota._get_api", return_value=mock_api),
        patch("tb.commands.ota.device_api", return_value=MagicMock()),
        patch("tb.commands.ota.raw_get", return_value=profile),
    ):
        result = runner.invoke(
            app, ["ota", "download", "--device-profile", PROFILE_UUID]
        )

    assert result.exit_code == 0, result.output
    mock_api.get_ota_package_info_by_id.assert_called_once_with(ota_package_id="fw-id")
    mock_api.download_ota_package.assert_called_once_with(ota_package_id="fw-id")


def test_download_by_profile_current_software(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.return_value = _mock_info(pkg_id="sw-id", pkg_type="SOFTWARE")
    mock_api.download_ota_package.return_value = b"SW"
    profile = {"firmwareId": {"id": "fw-id"}, "softwareId": {"id": "sw-id"}}

    with (
        patch("tb.commands.ota._get_api", return_value=mock_api),
        patch("tb.commands.ota.device_api", return_value=MagicMock()),
        patch("tb.commands.ota.raw_get", return_value=profile),
    ):
        result = runner.invoke(
            app, ["ota", "download", "--device-profile", PROFILE_UUID, "--type", "SOFTWARE"]
        )

    assert result.exit_code == 0, result.output
    mock_api.get_ota_package_info_by_id.assert_called_once_with(ota_package_id="sw-id")


def test_download_by_profile_name_resolves(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.return_value = _mock_info(pkg_id="fw-id")
    mock_api.download_ota_package.return_value = b"FW"
    profile = {"firmwareId": {"id": "fw-id"}}

    with (
        patch("tb.commands.ota._get_api", return_value=mock_api),
        patch("tb.commands.ota.device_api", return_value=MagicMock()),
        patch("tb.commands.ota.resolve_profile_id", return_value=PROFILE_UUID) as rp,
        patch("tb.commands.ota.raw_get", return_value=profile),
    ):
        result = runner.invoke(app, ["ota", "download", "--device-profile", "sensor-v2"])

    assert result.exit_code == 0, result.output
    rp.assert_called_once()


def test_download_by_profile_version(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pkg = _mock_info(pkg_id="v2", version="2.0")
    pkg.created_time = 200
    mock_api = MagicMock()
    mock_api.get_ota_packages1.return_value.data = [pkg]
    mock_api.download_ota_package.return_value = b"V2"

    with (
        patch("tb.commands.ota._get_api", return_value=mock_api),
        patch("tb.commands.ota.device_api", return_value=MagicMock()),
    ):
        result = runner.invoke(
            app, ["ota", "download", "--device-profile", PROFILE_UUID, "--version", "2.0"]
        )

    assert result.exit_code == 0, result.output
    mock_api.get_ota_packages1.assert_called_once_with(
        device_profile_id=PROFILE_UUID, type="FIRMWARE", page_size=100, page=0,
        text_search=None, sort_property=None, sort_order=None,
    )
    mock_api.download_ota_package.assert_called_once_with(ota_package_id="v2")


def test_download_by_profile_no_assignment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_api = MagicMock()
    profile = {"firmwareId": None, "softwareId": None}

    with (
        patch("tb.commands.ota._get_api", return_value=mock_api),
        patch("tb.commands.ota.device_api", return_value=MagicMock()),
        patch("tb.commands.ota.raw_get", return_value=profile),
    ):
        result = runner.invoke(app, ["ota", "download", "--device-profile", PROFILE_UUID])

    assert result.exit_code != 0
    assert "no FIRMWARE" in result.output
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_ota.py -k "by_profile" -q`
Expected: FAIL.

- [ ] **Step 3: Implement the `--device-profile` branch**

In `tb/commands/ota.py`, add the module-level UUID regex import and the helper:

```python
from tb.commands._client import _UUID_RE
```

```python
def _assigned_ota_id(entity, pkg_type, label):
    field = "firmwareId" if pkg_type == "FIRMWARE" else "softwareId"
    ref = entity.get(field)
    if not ref:
        typer.echo(f"{label} has no {pkg_type} package assigned.", err=True)
        raise typer.Exit(1)
    return ref["id"]
```

In `_resolve_package_info`, insert the `device_profile` branch before the `name` branch:

```python
    if device_profile:
        profile_id = (
            device_profile
            if _UUID_RE.match(device_profile)
            else resolve_profile_id(cfg_profile, device_profile)
        )
        if version:
            try:
                page = api.get_ota_packages1(
                    device_profile_id=profile_id, type=pkg_type, page_size=100, page=0,
                    text_search=None, sort_property=None, sort_order=None,
                )
            except Exception as e:
                _handle_api_error(e)
            return _select_from_candidates(
                list(page.data), version, f"profile '{device_profile}'"
            )
        try:
            profile = raw_get(device_api(cfg_profile), f"/api/deviceProfile/{profile_id}")
        except Exception as e:
            _handle_api_error(e)
        ota_id = _assigned_ota_id(profile, pkg_type, f"Profile '{device_profile}'")
        try:
            return api.get_ota_package_info_by_id(ota_package_id=ota_id)
        except Exception as e:
            _handle_api_error(e)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_ota.py -k "by_profile" -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Run full suite + lint, then commit**

Run: `uv run pytest -q && uv run ruff check tb/ tests/ && uv run ruff format tb/ tests/`

```bash
git add tb/commands/ota.py tests/test_ota.py
git commit -m "Resolve tb ota download by device profile"
```

---

### Task 5: Resolve by `--device`

**Files:**
- Modify: `tb/commands/ota.py`
- Test: `tests/test_ota.py`

**Interfaces:**
- Consumes: `_client.resolve_device_id`, `_client.device_api`, `_client.raw_get`; the `_select_from_candidates` and `_assigned_ota_id` helpers from Tasks 3–4; `get_ota_packages1`.
- Produces: the `--device` branch in `_resolve_package_info`, replacing the final "not implemented" stub.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_ota.py`:

```python
DEVICE_UUID = "22222222-2222-2222-2222-222222222222"


def test_download_by_device_current_direct(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.return_value = _mock_info(pkg_id="dev-fw")
    mock_api.download_ota_package.return_value = b"FW"
    device = {
        "firmwareId": {"id": "dev-fw"}, "softwareId": None,
        "deviceProfileId": {"id": PROFILE_UUID},
    }

    with (
        patch("tb.commands.ota._get_api", return_value=mock_api),
        patch("tb.commands.ota.resolve_device_id", return_value=DEVICE_UUID),
        patch("tb.commands.ota.device_api", return_value=MagicMock()),
        patch("tb.commands.ota.raw_get", return_value=device),
    ):
        result = runner.invoke(app, ["ota", "download", "--device", "thermostat-01"])

    assert result.exit_code == 0, result.output
    mock_api.download_ota_package.assert_called_once_with(ota_package_id="dev-fw")


def test_download_by_device_current_profile_fallback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id.return_value = _mock_info(pkg_id="prof-fw")
    mock_api.download_ota_package.return_value = b"FW"
    device = {
        "firmwareId": None, "softwareId": None,
        "deviceProfileId": {"id": PROFILE_UUID},
    }
    profile = {"firmwareId": {"id": "prof-fw"}, "softwareId": None}

    with (
        patch("tb.commands.ota._get_api", return_value=mock_api),
        patch("tb.commands.ota.resolve_device_id", return_value=DEVICE_UUID),
        patch("tb.commands.ota.device_api", return_value=MagicMock()),
        patch("tb.commands.ota.raw_get", side_effect=[device, profile]),
    ):
        result = runner.invoke(app, ["ota", "download", "--device", "thermostat-01"])

    assert result.exit_code == 0, result.output
    mock_api.download_ota_package.assert_called_once_with(ota_package_id="prof-fw")


def test_download_by_device_version(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pkg = _mock_info(pkg_id="v3", version="3.0")
    pkg.created_time = 300
    mock_api = MagicMock()
    mock_api.get_ota_packages1.return_value.data = [pkg]
    mock_api.download_ota_package.return_value = b"V3"
    device = {
        "firmwareId": {"id": "ignored"}, "softwareId": None,
        "deviceProfileId": {"id": PROFILE_UUID},
    }

    with (
        patch("tb.commands.ota._get_api", return_value=mock_api),
        patch("tb.commands.ota.resolve_device_id", return_value=DEVICE_UUID),
        patch("tb.commands.ota.device_api", return_value=MagicMock()),
        patch("tb.commands.ota.raw_get", return_value=device),
    ):
        result = runner.invoke(
            app, ["ota", "download", "--device", "thermostat-01", "--version", "3.0"]
        )

    assert result.exit_code == 0, result.output
    mock_api.get_ota_packages1.assert_called_once_with(
        device_profile_id=PROFILE_UUID, type="FIRMWARE", page_size=100, page=0,
        text_search=None, sort_property=None, sort_order=None,
    )
    mock_api.download_ota_package.assert_called_once_with(ota_package_id="v3")


def test_download_by_device_no_assignment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_api = MagicMock()
    device = {
        "firmwareId": None, "softwareId": None,
        "deviceProfileId": {"id": PROFILE_UUID},
    }
    profile = {"firmwareId": None, "softwareId": None}

    with (
        patch("tb.commands.ota._get_api", return_value=mock_api),
        patch("tb.commands.ota.resolve_device_id", return_value=DEVICE_UUID),
        patch("tb.commands.ota.device_api", return_value=MagicMock()),
        patch("tb.commands.ota.raw_get", side_effect=[device, profile]),
    ):
        result = runner.invoke(app, ["ota", "download", "--device", "thermostat-01"])

    assert result.exit_code != 0
    assert "no FIRMWARE" in result.output
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_ota.py -k "by_device" -q`
Expected: FAIL ("Selector not implemented yet.").

- [ ] **Step 3: Implement the `--device` branch**

In `_resolve_package_info`, replace the final stub (`typer.echo("Selector not implemented yet."...)` and its `raise`) with:

```python
    if device:
        device_id = resolve_device_id(cfg_profile, device)
        try:
            dev = raw_get(device_api(cfg_profile), f"/api/device/{device_id}")
        except Exception as e:
            _handle_api_error(e)
        profile_id = dev["deviceProfileId"]["id"]
        if version:
            try:
                page = api.get_ota_packages1(
                    device_profile_id=profile_id, type=pkg_type, page_size=100, page=0,
                    text_search=None, sort_property=None, sort_order=None,
                )
            except Exception as e:
                _handle_api_error(e)
            return _select_from_candidates(list(page.data), version, f"device '{device}'")
        field = "firmwareId" if pkg_type == "FIRMWARE" else "softwareId"
        ref = dev.get(field)
        if not ref:
            try:
                profile = raw_get(device_api(cfg_profile), f"/api/deviceProfile/{profile_id}")
            except Exception as e:
                _handle_api_error(e)
            ota_id = _assigned_ota_id(profile, pkg_type, f"Device '{device}' and its profile")
        else:
            ota_id = ref["id"]
        try:
            return api.get_ota_package_info_by_id(ota_package_id=ota_id)
        except Exception as e:
            _handle_api_error(e)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_ota.py -k "by_device" -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Run full suite + lint, then commit**

Run: `uv run pytest -q && uv run ruff check tb/ tests/ && uv run ruff format tb/ tests/`
Expected: all green (66 baseline + new download tests).

```bash
git add tb/commands/ota.py tests/test_ota.py
git commit -m "Resolve tb ota download by device with profile fallback"
```

---

### Task 6: Update README and CHANGELOG

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md` (if present)

**Interfaces:** none.

- [ ] **Step 1: Document the command**

Add a `tb ota download` subsection to the OTA section of `README.md` showing each selector form from the spec's signature table. If `CHANGELOG.md` exists, add a self-contained entry (no "now"/"again"/prior-state references): "Add `tb ota download` to fetch OTA package binaries by id, device profile, device, or title (current/latest or a specific version)."

- [ ] **Step 2: Verify docs build/read cleanly + commit**

Run: `uv run ruff format --check tb/ tests/` (sanity; docs are markdown).

```bash
git add README.md CHANGELOG.md 2>/dev/null; git commit -m "Document tb ota download command"
```

---

## Self-Review

**Spec coverage:**
- by id → Task 2. ✓
- by device-profile current/version, name resolution, no-assignment → Task 4. ✓
- by device current/fallback/version/no-assignment → Task 5. ✓
- by name latest/version, type filter, not-found → Task 3. ✓
- FIRMWARE default / `--type SOFTWARE` → Task 2 option + Tasks 3–5 filtering. ✓
- output default file_name / fallback / `--output` / refuse-overwrite / `--force` → Task 2. ✓
- validation (one selector, version+latest, latest-without-name, version-with-id, bad type) → Task 2. ✓
- raw-JSON device/profile reads (model/import limitation) → Task 1 extraction + Tasks 4–5 usage. ✓
- latest = newest created_time → Task 3 `_select_from_candidates`. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code and exact commands. The intentional `_resolve_package_info` stub is introduced in Task 2 and fully replaced by Task 5 (no stub remains at the end).

**Type consistency:** `_resolve_package_info` signature stable across tasks; `_select_from_candidates(candidates, version, label)` and `_assigned_ota_id(entity, pkg_type, label)` used identically where referenced; `raw_get`/`raw_json`/`resolve_profile_id` names match between `_client.py` (Task 1) and `ota.py` consumers (Tasks 4–5). `info.id.id`, `info.file_name`, `info.title`, `info.version`, `info.type`, `info.created_time` consistent with the typed `OtaPackageInfo` and the `_mock_info` fixture.

**Note on `--type` parameter name:** the Typer option is named `type` (shadowing the builtin) to match the existing `ota list`/`device list` convention in this codebase; `pkg_type` carries the validated upper-cased value internally.
