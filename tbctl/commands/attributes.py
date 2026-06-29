import json
from datetime import datetime, timezone

import typer

from tbctl.commands._client import (
    handle_api_error,
    parse_response,
    resolve_device_id,
    telemetry_api,
)

app = typer.Typer(no_args_is_help=True, help="Read device attributes.")

SCOPES = ("CLIENT_SCOPE", "SERVER_SCOPE", "SHARED_SCOPE")


def _fmt_ts(ms) -> str:
    if ms is None:
        return "-"
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


@app.command("get")
def get_attributes(
    ctx: typer.Context,
    device: str = typer.Argument(help="Device UUID or name."),
    scope: str = typer.Option(None, "--scope", help=f"Limit to one scope: {', '.join(SCOPES)}."),
    keys: str = typer.Option(None, "--keys", "-k", help="Comma-separated attribute keys."),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON."),
):
    if scope and scope not in SCOPES:
        typer.echo(f"--scope must be one of {', '.join(SCOPES)}.", err=True)
        raise typer.Exit(1)

    profile = ctx.obj["profile"]
    device_id = resolve_device_id(profile, device)
    api = telemetry_api(profile)
    try:
        if scope:
            result = api.get_attributes_by_scope("DEVICE", device_id, scope, {}, keys=keys)
        else:
            result = api.get_attributes("DEVICE", device_id, {}, keys=keys)
    except Exception as e:
        handle_api_error(e)

    result = parse_response(result)

    if output_json:
        typer.echo(json.dumps(result, indent=2, default=str))
        return

    if not result:
        typer.echo("No attributes found.")
        return

    from rich.console import Console
    from rich.table import Table

    table = Table(show_header=True, header_style="bold")
    table.add_column("Key")
    table.add_column("Value")
    table.add_column("Last update (UTC)")
    for a in sorted(result, key=lambda x: x.get("key", "")):
        table.add_row(
            str(a.get("key", "")),
            str(a.get("value", "")),
            _fmt_ts(a.get("lastUpdateTs")),
        )
    Console().print(table)
