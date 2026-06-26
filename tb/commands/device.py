import json
from datetime import datetime, timezone

import typer

from tb.commands._client import device_api, handle_api_error, resolve_device_id

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
