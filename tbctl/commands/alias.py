import json

import typer

import tbctl.aliases as aliases

app = typer.Typer(no_args_is_help=True, help="Manage local device aliases.")


@app.command("add")
def add_alias(
    ctx: typer.Context,
    name: str = typer.Argument(help="Free-text alias, e.g. ruedi."),
    target: str = typer.Argument(help="Device name the alias points at."),
    device_id: str = typer.Option(
        None, "--id", help="Device UUID, so resolving skips the device-name lookup."
    ),
):
    """Point a free-text alias at a device, replacing any existing entry."""
    try:
        previous = aliases.add(ctx.obj["profile"], name, target, device_id)
    except ValueError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)
    shown = f"{target} ({device_id})" if device_id else target
    suffix = f" (was {previous.name})" if previous else ""
    typer.echo(f"Alias '{name}' -> {shown}{suffix}")


@app.command("list")
def list_aliases(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON."),
):
    profile = ctx.obj["profile"]
    table = aliases.load(profile)

    if output_json:
        typer.echo(json.dumps({a: e._asdict() for a, e in table.items()}, indent=2))
        return
    if not table:
        typer.echo(f"No aliases for profile '{profile}'.")
        return

    from rich.console import Console
    from rich.table import Table

    with_uuid = any(entry.id for entry in table.values())
    rendered = Table(show_header=True, header_style="bold")
    rendered.add_column("Alias")
    rendered.add_column("Device")
    if with_uuid:
        rendered.add_column("UUID")
    for alias, entry in sorted(table.items()):
        row = [alias, entry.name]
        if with_uuid:
            row.append(entry.id or "")
        rendered.add_row(*row)
    Console().print(rendered)


@app.command("rm")
def remove_alias(
    ctx: typer.Context,
    name: str = typer.Argument(help="Alias to remove.", autocompletion=aliases.complete_device),
):
    if not aliases.remove(ctx.obj["profile"], name):
        typer.echo(f"Alias '{name}' not found.", err=True)
        raise typer.Exit(1)
    typer.echo(f"Removed alias '{name}'")
