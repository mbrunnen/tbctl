import json

import typer

import tbctl.aliases as aliases

app = typer.Typer(no_args_is_help=True, help="Manage local device aliases.")


@app.command("add")
def add_alias(
    ctx: typer.Context,
    name: str = typer.Argument(help="Free-text alias, e.g. ruedi."),
    target: str = typer.Argument(help="Device name or UUID the alias points at."),
):
    """Point a free-text alias at a device, overwriting any existing target."""
    previous = aliases.add(ctx.obj["profile"], name, target)
    suffix = f" (was {previous})" if previous else ""
    typer.echo(f"Alias '{name}' -> {target}{suffix}")


@app.command("list")
def list_aliases(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON."),
):
    profile = ctx.obj["profile"]
    table = aliases.load(profile)

    if output_json:
        typer.echo(json.dumps(table, indent=2))
        return
    if not table:
        typer.echo(f"No aliases for profile '{profile}'.")
        return

    from rich.console import Console
    from rich.table import Table

    rendered = Table(show_header=True, header_style="bold")
    rendered.add_column("Alias")
    rendered.add_column("Device")
    for alias, device in sorted(table.items()):
        rendered.add_row(alias, device)
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
