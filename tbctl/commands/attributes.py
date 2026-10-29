import json

import typer

import tbctl.aliases as aliases
from tbctl import keycache
from tbctl.commands._client import (
    handle_api_error,
    parse_response,
    resolve_device_id,
    telemetry_api,
)
from tbctl.commands._format import fmt_ts, fmt_value, ts_header

app = typer.Typer(no_args_is_help=True, help="Read device attributes.")

SCOPES = ("CLIENT_SCOPE", "SERVER_SCOPE", "SHARED_SCOPE")
SHORT_SCOPES = ("client", "server", "shared")


def normalise_scope(value: str) -> str | None:
    """Map ``server``, ``Server`` or ``SERVER_SCOPE`` to ``SERVER_SCOPE``; ``None`` if unknown."""
    scope = value.strip().upper()
    if not scope.endswith("_SCOPE"):
        scope += "_SCOPE"
    return scope if scope in SCOPES else None


def complete_scope(incomplete: str) -> list[str]:
    return [s for s in SHORT_SCOPES if s.startswith(incomplete)]


@app.command("get")
def get_attributes(
    ctx: typer.Context,
    device: str = typer.Argument(
        help="Device UUID or name.", autocompletion=aliases.complete_device
    ),
    scope: str = typer.Option(
        "shared",
        "--scope",
        help="Attribute scope: client, server or shared.",
        autocompletion=complete_scope,
    ),
    keys: str = typer.Option(
        None,
        "--keys",
        "-k",
        help="Comma-separated attribute keys.",
        autocompletion=keycache.complete_attribute_keys,
    ),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON."),
    local: bool = typer.Option(
        False, "--local", help="Show timestamps in local time instead of UTC."
    ),
):
    canonical = normalise_scope(scope)
    if not canonical:
        typer.echo(f"--scope must be one of {', '.join(SHORT_SCOPES)}.", err=True)
        raise typer.Exit(1)

    profile = ctx.obj["profile"]
    device_id = resolve_device_id(profile, device)
    try:
        result = parse_response(
            telemetry_api(profile).get_attributes_by_scope(
                "DEVICE", device_id, canonical, {}, keys=keys
            )
        )
    except Exception as e:
        handle_api_error(e)
    keycache.record(
        profile, device, device_id, canonical, (a["key"] for a in result), full=not keys
    )

    if output_json:
        typer.echo(json.dumps(result, indent=2, default=str))
        return

    if not result:
        typer.echo("No attributes found.")
        return

    from rich.console import Console
    from rich.table import Table

    table = Table(
        show_header=True, header_style="bold", title=canonical.removesuffix("_SCOPE").lower()
    )
    table.add_column("Key")
    table.add_column("Value")
    table.add_column(ts_header("Last update", local))
    for a in sorted(result, key=lambda x: x.get("key", "")):
        table.add_row(
            str(a.get("key", "")),
            fmt_value(a.get("value", "")),
            fmt_ts(a.get("lastUpdateTs"), local),
        )
    Console().print(table)
