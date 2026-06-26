import json
from datetime import datetime, timezone

import typer

from tb.commands._client import (
    device_api,
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


def _raw_get(api, resource_path, query=None):
    """GET a path via the device client and return parsed JSON.

    Used for device-profile lookups: the generated device-profile controller
    cannot be imported (a circular import in its alarm-condition models), so we
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
    return _raw_json(response)


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
    api = device_api(profile)
    try:
        if name == "default":
            return _raw_get(api, "/api/deviceProfileInfo/default")["id"]["id"]
        page = _raw_get(
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


def _save_device_raw(api, body):
    """Save a device from a plain dict, bypassing the Device model.

    The generated Device model both fails to import cleanly (circular import)
    and cannot round-trip ``deviceData`` (undiscriminated ``oneOf``). Building a
    plain dict and serialising it through the endpoint's own request builder
    avoids the model entirely on both the request and response sides.
    """
    request = api._save_device_serialize(
        device=body,
        access_token=None,
        entity_group_id=None,
        entity_group_ids=None,
        name_conflict_policy=None,
        uniquify_separator=None,
        uniquify_strategy=None,
        _request_auth=None,
        _content_type=None,
        _headers=None,
        _host_index=0,
    )
    response = api.api_client.call_api(*request)
    response.read()
    return _raw_json(response)


@app.command("create")
def create_device(
    ctx: typer.Context,
    name: str = typer.Argument(help="Unique device name."),
    label: str = typer.Option(None, "--label", help="Display label."),
    profile: str = typer.Option("default", "--profile", help="Device profile name."),
):
    cfg_profile = ctx.obj["profile"]
    profile_id = resolve_profile_id(cfg_profile, profile)
    api = device_api(cfg_profile)
    body = {
        "name": name,
        "label": label,
        "deviceProfileId": {"id": profile_id, "entityType": "DEVICE_PROFILE"},
    }
    try:
        created = _save_device_raw(api, body)
    except Exception as e:
        handle_api_error(e)
    typer.echo(f"Created {created['id']['id']}")


@app.command("update")
def update_device(
    ctx: typer.Context,
    device: str = typer.Argument(help="Device UUID or name."),
    name: str = typer.Option(None, "--name", help="New device name."),
    label: str = typer.Option(None, "--label", help="New display label."),
    profile: str = typer.Option(None, "--profile", help="New device profile name."),
):
    cfg_profile = ctx.obj["profile"]
    device_id = resolve_device_id(cfg_profile, device)
    api = device_api(cfg_profile)
    try:
        response = api.get_device_by_id_without_preload_content(device_id=device_id)
        existing = _raw_json(response)
    except Exception as e:
        handle_api_error(e)

    if name is not None:
        existing["name"] = name
    if label is not None:
        existing["label"] = label
    if profile is not None:
        existing["deviceProfileId"] = {
            "id": resolve_profile_id(cfg_profile, profile),
            "entityType": "DEVICE_PROFILE",
        }

    try:
        _save_device_raw(api, existing)
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
