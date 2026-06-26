import json
from datetime import datetime, timezone

import typer

from tb.commands._client import (
    device_api,
    device_profile_api,
    handle_api_error,
    owner_api,
    resolve_device_id,
)

app = typer.Typer(no_args_is_help=True, help="Manage devices.")


def _fmt_ts(ms) -> str:
    if not ms:
        return "-"
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _raw_json(response):
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


def _device_access_token(api, device_id):
    try:
        return api.get_device_credentials_by_device_id(device_id=device_id).credentials_id
    except Exception as e:
        handle_api_error(e)


@app.command("list")
def list_devices(
    ctx: typer.Context,
    page_size: int = typer.Option(20, "--page-size", help="Devices per page."),
    text_search: str = typer.Option(None, "--search", "-s", help="Substring filter on name."),
    type: str = typer.Option(None, "--type", "-t", help="Filter by device profile name."),
    customer: str = typer.Option(
        None, "--customer", "-c", help="Only devices owned by this customer UUID."
    ),
    token: bool = typer.Option(False, "--token", help="Include each device's access token."),
    sort_property: str = typer.Option(None, "--sort-by", help="Property to sort by."),
    sort_order: str = typer.Option(None, "--sort-order", help="ASC or DESC."),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON."),
):
    api = device_api(ctx.obj["profile"])
    try:
        if customer:
            response = api.get_customer_devices_without_preload_content(
                customer_id=customer,
                page_size=page_size,
                page=0,
                type=type,
                text_search=text_search,
            )
        else:
            response = api.get_tenant_devices_without_preload_content(
                page_size=page_size,
                page=0,
                type=type,
                text_search=text_search,
                sort_property=sort_property,
                sort_order=sort_order,
            )
        page = _raw_json(response)
    except Exception as e:
        handle_api_error(e)

    devices = page.get("data", [])

    if token:
        for d in devices:
            d["accessToken"] = _device_access_token(api, (d.get("id") or {}).get("id"))

    if not devices:
        typer.echo("[]" if output_json else "No devices found.")
        return

    if output_json:
        typer.echo(json.dumps(devices, indent=2))
        return

    from rich.console import Console
    from rich.table import Table

    table = Table(show_header=True, header_style="bold")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("Label")
    table.add_column("Created (UTC)")
    if token:
        table.add_column("Access token")
    for d in devices:
        row = [
            (d.get("id") or {}).get("id", ""),
            d.get("name") or "",
            d.get("type") or "",
            d.get("label") or "",
            _fmt_ts(d.get("createdTime")),
        ]
        if token:
            row.append(d.get("accessToken") or "")
        table.add_row(*row)
    console = Console()
    console.print(table)
    console.print(f"Showing {len(devices)} of {page.get('totalElements', len(devices))} devices")


@app.command("get")
def get_device(ctx: typer.Context, device: str = typer.Argument(help="Device UUID or name.")):
    cfg_profile = ctx.obj["profile"]
    device_id = resolve_device_id(cfg_profile, device)
    api = device_api(cfg_profile)
    try:
        response = api.get_device_by_id_without_preload_content(device_id=device_id)
        data = _raw_json(response)
    except Exception as e:
        handle_api_error(e)
    typer.echo(json.dumps(data, indent=2))


def resolve_profile_id(profile: str, name: str) -> str:
    api = device_profile_api(profile)
    try:
        if name == "default":
            info = api.get_default_device_profile_info()
            return str(info.id.id)
        result = api.get_device_profile_infos(page_size=100, page=0, text_search=name)
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


@app.command("assign")
def assign_device(
    ctx: typer.Context,
    device: str = typer.Argument(help="Device UUID or name."),
    customer: str = typer.Option(..., "--customer", "-c", help="Customer UUID to own the device."),
):
    cfg_profile = ctx.obj["profile"]
    device_id = resolve_device_id(cfg_profile, device)
    api = owner_api(cfg_profile)
    try:
        api.change_owner_to_customer(owner_id=customer, entity_type="DEVICE", entity_id=device_id)
    except Exception as e:
        handle_api_error(e)
    typer.echo(f"Assigned {device_id} to customer {customer}")
