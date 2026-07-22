import hashlib
import json
from pathlib import Path

import typer

import tbctl.config as cfg
from tbctl.commands._client import (
    _UUID_RE,
    _save_device_raw,
    device_api,
    handle_api_error,
    profile_name_map,
    raw_get,
    raw_post,
    resolve_device_id,
    resolve_profile_id,
)

app = typer.Typer(no_args_is_help=True, help="Manage OTA packages.")


def _format_size(size_bytes) -> str:
    if size_bytes is None:
        return "-"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024**2:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / 1024**2:.1f} MB"


def _get_api(profile: str):
    try:
        from tb_client.api.ota_package_controller_api import OtaPackageControllerApi
        from tb_client.configuration import Configuration
        from tbctl.commands._client import make_api_client
    except ImportError:
        typer.echo("tb_client not found. Run ./generate.sh to generate the client.", err=True)
        raise typer.Exit(1)

    conf = cfg.load(profile)
    if not conf.get("url") or not conf.get("token"):
        typer.echo(f"Profile '{profile}' not configured. Run `tbctl config set-url`.", err=True)
        raise typer.Exit(1)

    configuration = Configuration(host=conf["url"].rstrip("/"))
    configuration.api_key = {"API key form": conf["token"]}
    configuration.api_key_prefix = {"API key form": "ApiKey"}
    return OtaPackageControllerApi(make_api_client(configuration))


_PAGE_SIZE = 100


@app.command("list")
def list_packages(
    ctx: typer.Context,
    page_size: int = typer.Option(20, "--page-size", help="Packages per page."),
    text_search: str = typer.Option(None, "--search", "-s", help="Substring filter on title."),
    version: str = typer.Option(
        None, "--version", help="Filter by version (client-side, case-insensitive substring)."
    ),
    device_profile: str = typer.Option(
        None, "--device-profile", "-p", help="Filter by device profile name or UUID."
    ),
    type: str = typer.Option(
        None, "--type", "-t", help="Filter by type: FIRMWARE or SOFTWARE (needs --device-profile)."
    ),
    sort_property: str = typer.Option(None, "--sort-by", help="Property to sort by."),
    sort_order: str = typer.Option(None, "--sort-order", help="ASC or DESC."),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON."),
):
    from rich.console import Console
    from rich.table import Table

    if type and not device_profile:
        typer.echo("--type requires --device-profile.", err=True)
        raise typer.Exit(1)

    cfg_profile = ctx.obj["profile"]
    api = _get_api(cfg_profile)

    device_profile_id = None
    if device_profile:
        device_profile_id = (
            device_profile
            if _UUID_RE.match(device_profile)
            else resolve_profile_id(cfg_profile, device_profile)
        )

    types = ([type] if type else ["FIRMWARE", "SOFTWARE"]) if device_profile_id else None

    def _fetch(page, size):
        """Return ``(data, total)`` for one page, across every requested type."""
        if device_profile_id:
            data = []
            total = 0
            for t in types:
                result = api.get_ota_packages1(
                    device_profile_id=device_profile_id,
                    type=t,
                    page_size=size,
                    page=page,
                    text_search=text_search,
                    sort_property=sort_property,
                    sort_order=sort_order,
                )
                data.extend(result.data or [])
                total += result.total_elements or 0
            return data, total
        result = api.get_ota_packages(
            page_size=size,
            page=page,
            text_search=text_search,
            sort_property=sort_property,
            sort_order=sort_order,
        )
        return list(result.data or []), result.total_elements or 0

    try:
        if version:
            data = []
            total = 0
            page = 0
            while True:
                page_data, total = _fetch(page, _PAGE_SIZE)
                data.extend(page_data)
                if not page_data or len(data) >= total:
                    break
                page += 1
            needle = version.lower()
            data = [pkg for pkg in data if needle in (pkg.version or "").lower()]
        else:
            data, total = _fetch(0, page_size)
    except Exception as e:
        handle_api_error(e)

    if not data:
        typer.echo("[]" if output_json else "No OTA packages found.")
        return

    if output_json:
        typer.echo(
            json.dumps(
                [pkg.model_dump(by_alias=True, exclude_none=True) for pkg in data],
                indent=2,
                default=str,
            )
        )
        return

    profile_names = profile_name_map(api)

    table = Table(show_header=True, header_style="bold")
    table.add_column("ID")
    table.add_column("Title")
    table.add_column("Version")
    table.add_column("Type")
    table.add_column("Device Profile")
    table.add_column("Size", justify="right")

    for pkg in data:
        pkg_id = str(pkg.id.id) if pkg.id is not None else ""
        dp = getattr(pkg, "device_profile_id", None)
        dp_id = str(dp.id) if dp is not None else None
        profile_label = profile_names.get(dp_id, dp_id) if dp_id else "-"
        table.add_row(
            pkg_id,
            pkg.title or "",
            pkg.version or "",
            pkg.type or "",
            profile_label,
            _format_size(getattr(pkg, "data_size", None)),
        )

    console = Console()
    console.print(table)
    console.print(f"Showing {len(data)} of {total} packages")


_HASHLIB_ALGOS = {"MD5": "md5", "SHA256": "sha256", "SHA384": "sha384", "SHA512": "sha512"}


def _compute_checksum(data: bytes, algorithm: str):
    name = _HASHLIB_ALGOS.get(algorithm)
    if name is None:
        return None
    return hashlib.new(name, data).hexdigest()


def _info_body(*, title, version, pkg_type, profile_id, content_type, url):
    """Build the OTA package info body.

    For file uploads the body stays minimal: ThingsBoard sets fileName,
    checksumAlgorithm, contentType and dataSize from the data upload and rejects
    an info request that tries to set them up front.
    """
    body = {
        "title": title,
        "version": version,
        "type": pkg_type,
        "usesUrl": bool(url),
    }
    if url:
        body["url"] = url
        if content_type:
            body["contentType"] = content_type
    if profile_id:
        body["deviceProfileId"] = {"id": profile_id, "entityType": "DEVICE_PROFILE"}
    return body


@app.command("upload")
def upload_package(
    ctx: typer.Context,
    file: str = typer.Argument(None, help="Path to the firmware/software file."),
    title: str = typer.Option(..., "--title", "-T", help="OTA package title."),
    version: str = typer.Option(..., "--version", "-v", help="OTA package version."),
    type: str = typer.Option("FIRMWARE", "--type", "-t", help="FIRMWARE or SOFTWARE."),
    device_profile: str = typer.Option(
        ..., "--device-profile", "-p", help="Device profile name or UUID (required by ThingsBoard)."
    ),
    url: str = typer.Option(None, "--url", help="URL of an externally hosted package."),
    checksum_algorithm: str = typer.Option(
        "SHA256", "--checksum-algorithm", help="Checksum algorithm for file uploads."
    ),
    content_type: str = typer.Option(None, "--content-type", help="OTA package content type."),
):
    pkg_type = type.upper()
    if pkg_type not in ("FIRMWARE", "SOFTWARE"):
        typer.echo("--type must be FIRMWARE or SOFTWARE.", err=True)
        raise typer.Exit(1)
    if bool(file) == bool(url):
        typer.echo("Provide exactly one source: a FILE argument or --url.", err=True)
        raise typer.Exit(1)

    cfg_profile = ctx.obj["profile"]
    api = _get_api(cfg_profile)

    profile_id = None
    if device_profile:
        profile_id = (
            device_profile
            if _UUID_RE.match(device_profile)
            else resolve_profile_id(cfg_profile, device_profile)
        )

    algorithm = checksum_algorithm.upper()
    data = None
    checksum = None
    file_name = None
    if file:
        path = Path(file)
        if not path.is_file():
            typer.echo(f"{path} is not a file.", err=True)
            raise typer.Exit(1)
        data = path.read_bytes()
        checksum = _compute_checksum(data, algorithm)
        file_name = path.name

    body = _info_body(
        title=title,
        version=version,
        pkg_type=pkg_type,
        profile_id=profile_id,
        content_type=content_type,
        url=url,
    )
    try:
        saved = raw_post(api, "/api/otaPackage", body)
    except Exception as e:
        handle_api_error(e)
    pkg_id = saved["id"]["id"]

    if url:
        typer.echo(f"Created OTA package {pkg_id} ({title} {version}) -> {url}")
        return

    try:
        api.save_ota_package_data(
            ota_package_id=str(pkg_id),
            checksum_algorithm=algorithm,
            file=(file_name, data),
            checksum=checksum,
        )
    except Exception as e:
        # The info package is already persisted; drop it so its title+version
        # does not block a retry.
        try:
            api.delete_ota_package(ota_package_id=str(pkg_id))
        except Exception:
            pass
        handle_api_error(e)
    typer.echo(
        f"Created OTA package {pkg_id} ({title} {version}), uploaded {_format_size(len(data))}"
    )


@app.command("get")
def get_package(ctx: typer.Context, id: str = typer.Argument(help="OTA package UUID.")):
    api = _get_api(ctx.obj["profile"])
    try:
        pkg = api.get_ota_package_info_by_id(ota_package_id=id)
    except Exception as e:
        handle_api_error(e)
    typer.echo(json.dumps(pkg.to_dict(), indent=2, default=str))


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


def _assigned_ota_id(entity, pkg_type, label):
    field = "firmwareId" if pkg_type == "FIRMWARE" else "softwareId"
    ref = entity.get(field)
    if not ref:
        typer.echo(f"{label} has no {pkg_type} package assigned.", err=True)
        raise typer.Exit(1)
    return ref["id"]


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


def _packages_for_profile(api, profile_id, pkg_type):
    try:
        page = api.get_ota_packages1(
            device_profile_id=profile_id,
            type=pkg_type,
            page_size=100,
            page=0,
            text_search=None,
            sort_property=None,
            sort_order=None,
        )
    except Exception as e:
        handle_api_error(e)
    return list(page.data)


def _resolve_package_info(
    cfg_profile, *, package_id, device_profile, device, name, version, latest, pkg_type
):
    api = _get_api(cfg_profile)
    if package_id:
        try:
            return api, api.get_ota_package_info_by_id(ota_package_id=package_id)
        except Exception as e:
            handle_api_error(e)
    if device_profile:
        profile_id = (
            device_profile
            if _UUID_RE.match(device_profile)
            else resolve_profile_id(cfg_profile, device_profile)
        )
        if version:
            candidates = _packages_for_profile(api, profile_id, pkg_type)
            return api, _select_from_candidates(candidates, version, f"profile '{device_profile}'")
        try:
            profile = raw_get(device_api(cfg_profile), f"/api/deviceProfile/{profile_id}")
        except Exception as e:
            handle_api_error(e)
        ota_id = _assigned_ota_id(profile, pkg_type, f"Profile '{device_profile}'")
        try:
            return api, api.get_ota_package_info_by_id(ota_package_id=ota_id)
        except Exception as e:
            handle_api_error(e)
    if name:
        try:
            page = api.get_ota_packages(
                page_size=100,
                page=0,
                text_search=name,
                sort_property=None,
                sort_order=None,
            )
        except Exception as e:
            handle_api_error(e)
        candidates = [
            p
            for p in page.data
            if (p.title or "").lower() == name.lower() and (p.type or "") == pkg_type
        ]
        return api, _select_from_candidates(candidates, version, f"name '{name}'")
    if device:
        device_id = resolve_device_id(cfg_profile, device)
        try:
            dev = raw_get(device_api(cfg_profile), f"/api/device/{device_id}")
        except Exception as e:
            handle_api_error(e)
        profile_id = dev["deviceProfileId"]["id"]
        if version:
            candidates = _packages_for_profile(api, profile_id, pkg_type)
            return api, _select_from_candidates(candidates, version, f"device '{device}'")
        ref = dev.get("firmwareId" if pkg_type == "FIRMWARE" else "softwareId")
        if not ref:
            try:
                profile = raw_get(device_api(cfg_profile), f"/api/deviceProfile/{profile_id}")
            except Exception as e:
                handle_api_error(e)
            ota_id = _assigned_ota_id(profile, pkg_type, f"Device '{device}' and its profile")
        else:
            ota_id = ref["id"]
        try:
            return api, api.get_ota_package_info_by_id(ota_package_id=ota_id)
        except Exception as e:
            handle_api_error(e)
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
    device: str = typer.Option(None, "--device", "-D", help="Resolve via device name or UUID."),
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
    api, info = _resolve_package_info(
        cfg_profile,
        package_id=package_id,
        device_profile=device_profile,
        device=device,
        name=name,
        version=version,
        latest=latest,
        pkg_type=pkg_type,
    )
    try:
        data = api.download_ota_package(ota_package_id=str(info.id.id))
    except Exception as e:
        handle_api_error(e)
    _write_package(info, data, output, force)


@app.command("delete")
def delete_package(
    ctx: typer.Context,
    id: str = typer.Argument(help="OTA package UUID."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
):
    if not yes:
        typer.confirm(f"Delete OTA package {id}?", abort=True)
    api = _get_api(ctx.obj["profile"])
    try:
        api.delete_ota_package(ota_package_id=id)
    except Exception as e:
        handle_api_error(e)
    typer.echo(f"Deleted {id}")


@app.command("assign")
def assign_package(
    ctx: typer.Context,
    package: str = typer.Argument(help="OTA package UUID or title."),
    device: str = typer.Argument(help="Device UUID or name."),
    version: str = typer.Option(None, "--version", "-v", help="Package version (with a title)."),
    latest: bool = typer.Option(False, "--latest", help="Newest version (with a title)."),
    type: str = typer.Option("FIRMWARE", "--type", "-t", help="FIRMWARE or SOFTWARE."),
):
    pkg_type = type.upper()
    if pkg_type not in ("FIRMWARE", "SOFTWARE"):
        typer.echo("--type must be FIRMWARE or SOFTWARE.", err=True)
        raise typer.Exit(1)

    by_id = bool(_UUID_RE.match(package))
    if by_id and version:
        typer.echo("--version cannot be combined with a package UUID.", err=True)
        raise typer.Exit(1)
    if version and latest:
        typer.echo("--version and --latest are mutually exclusive.", err=True)
        raise typer.Exit(1)

    cfg_profile = ctx.obj["profile"]
    api, info = _resolve_package_info(
        cfg_profile,
        package_id=package if by_id else None,
        device_profile=None,
        device=None,
        name=None if by_id else package,
        version=version,
        latest=latest,
        pkg_type=pkg_type,
    )
    if (info.type or "") != pkg_type:
        typer.echo(f"Package '{info.title}' is {info.type}, not {pkg_type}.", err=True)
        raise typer.Exit(1)

    dev_api = device_api(cfg_profile)
    device_id = resolve_device_id(cfg_profile, device)
    try:
        dev = raw_get(dev_api, f"/api/device/{device_id}")
    except Exception as e:
        handle_api_error(e)
    field = "firmwareId" if pkg_type == "FIRMWARE" else "softwareId"
    dev[field] = {"id": str(info.id.id), "entityType": "OTA_PACKAGE"}
    try:
        _save_device_raw(dev_api, dev)
    except Exception as e:
        handle_api_error(e)
    typer.echo(f"Assigned {info.title} {info.version} to {device_id}")


@app.command("unassign")
def unassign_package(
    ctx: typer.Context,
    device: str = typer.Argument(help="Device UUID or name."),
    type: str = typer.Option("FIRMWARE", "--type", "-t", help="FIRMWARE or SOFTWARE."),
):
    pkg_type = type.upper()
    if pkg_type not in ("FIRMWARE", "SOFTWARE"):
        typer.echo("--type must be FIRMWARE or SOFTWARE.", err=True)
        raise typer.Exit(1)

    cfg_profile = ctx.obj["profile"]
    dev_api = device_api(cfg_profile)
    device_id = resolve_device_id(cfg_profile, device)
    try:
        dev = raw_get(dev_api, f"/api/device/{device_id}")
    except Exception as e:
        handle_api_error(e)
    field = "firmwareId" if pkg_type == "FIRMWARE" else "softwareId"
    if not dev.get(field):
        typer.echo(f"{device_id} has no {pkg_type} package assigned.")
        raise typer.Exit(0)
    dev[field] = None
    try:
        _save_device_raw(dev_api, dev)
    except Exception as e:
        handle_api_error(e)
    typer.echo(f"Cleared {pkg_type} assignment from {device_id}")
