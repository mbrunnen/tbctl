import json
from collections.abc import Iterable

import typer

import tbctl.aliases as aliases
from tbctl import config, keycache
from tbctl.commands._client import (
    handle_api_error,
    parse_response,
    resolve_device_id,
    telemetry_api,
)
from tbctl.commands._format import fmt_ts, fmt_value, ts_header

app = typer.Typer(no_args_is_help=True, help="Read and write device attributes.")

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


def _scope_or_exit(scope: str) -> str:
    canonical = normalise_scope(scope)
    if not canonical:
        typer.echo(f"--scope must be one of {', '.join(SHORT_SCOPES)}.", err=True)
        raise typer.Exit(1)
    return canonical


def _short(scope: str) -> str:
    return scope.removesuffix("_SCOPE").lower()


def _write_scope(scope: str) -> str:
    canonical = _scope_or_exit(scope)
    if canonical == "CLIENT_SCOPE":
        typer.echo(
            "Client attributes are written by the device; use --scope server or shared.",
            err=True,
        )
        raise typer.Exit(1)
    return canonical


def protected_keys(profile: str) -> set[str]:
    protected = config.load(profile).get("protected_attributes", [])
    return {protected} if isinstance(protected, str) else set(protected)


def _refuse_protected(profile: str, keys: Iterable[str]) -> None:
    hits = protected_keys(profile).intersection(keys)
    if hits:
        typer.echo(
            f"Refusing to change protected attribute(s): {', '.join(sorted(hits))}.", err=True
        )
        raise typer.Exit(1)


def _parse_pairs(pairs: list[str]) -> list[tuple[str, object]]:
    parsed = []
    for pair in pairs:
        key, sep, raw = pair.partition("=")
        if not sep or not key:
            raise typer.BadParameter(f"'{pair}' is not key=value.")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = raw
        parsed.append((key, value))
    return parsed


def _scope_option() -> typer.models.OptionInfo:
    return typer.Option(
        "shared",
        "--scope",
        help="Attribute scope: client, server or shared.",
        autocompletion=complete_scope,
    )


@app.command("get")
def get_attributes(
    ctx: typer.Context,
    device: str = typer.Argument(
        help="Device UUID or name.", autocompletion=aliases.complete_device
    ),
    scope: str = _scope_option(),
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
    canonical = _scope_or_exit(scope)
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

    table = Table(show_header=True, header_style="bold", title=_short(canonical))
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


@app.command("keys")
def list_keys(
    ctx: typer.Context,
    device: str = typer.Argument(
        help="Device UUID or name.", autocompletion=aliases.complete_device
    ),
    scope: str = _scope_option(),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON."),
):
    canonical = _scope_or_exit(scope)
    profile = ctx.obj["profile"]
    device_id = resolve_device_id(profile, device)
    try:
        keys = parse_response(
            telemetry_api(profile).get_attribute_keys_by_scope("DEVICE", device_id, canonical)
        )
    except Exception as e:
        handle_api_error(e)
    keycache.record(profile, device, device_id, canonical, keys, full=True)

    if output_json:
        typer.echo(json.dumps(keys, indent=2, default=str))
        return
    typer.echo("\n".join(sorted(keys)) if keys else f"No {_short(canonical)} attribute keys found.")


@app.command("set")
def set_attributes(
    ctx: typer.Context,
    device: str = typer.Argument(
        help="Device UUID or name.", autocompletion=aliases.complete_device
    ),
    pairs: list[str] = typer.Argument(
        help="key=value pairs; a value is parsed as JSON, else taken as text.",
        callback=_parse_pairs,
    ),
    scope: str = _scope_option(),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON."),
):
    canonical = _write_scope(scope)
    data = dict(pairs)
    profile = ctx.obj["profile"]
    _refuse_protected(profile, data)
    device_id = resolve_device_id(profile, device)
    try:
        telemetry_api(profile).save_device_attributes(device_id, canonical, json.dumps(data))
    except Exception as e:
        handle_api_error(e)
    keycache.record(profile, device, device_id, canonical, data, full=False)

    if output_json:
        typer.echo(json.dumps(data, indent=2, default=str))
        return
    typer.echo(f"Set {', '.join(data)} on {device} ({_short(canonical)}).")


@app.command("delete")
def delete_attributes(
    ctx: typer.Context,
    device: str = typer.Argument(
        help="Device UUID or name.", autocompletion=aliases.complete_device
    ),
    keys: list[str] = typer.Argument(help="Attribute keys to delete."),
    scope: str = _scope_option(),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
):
    canonical = _write_scope(scope)
    profile = ctx.obj["profile"]
    _refuse_protected(profile, keys)
    device_id = resolve_device_id(profile, device)
    names = ", ".join(keys)
    if not yes:
        typer.confirm(f"Delete {names} from {device} ({_short(canonical)})?", abort=True)
    try:
        telemetry_api(profile).delete_device_attributes(
            device_id, canonical, {}, keys=",".join(keys)
        )
    except Exception as e:
        handle_api_error(e)
    typer.echo(f"Deleted {names} from {device} ({_short(canonical)}).")
