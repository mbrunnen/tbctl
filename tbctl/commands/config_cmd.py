import json

import typer

import tbctl.config as cfg

app = typer.Typer(no_args_is_help=True, help="Show CLI configuration.")


def _flatten(data: dict, prefix: str = ""):
    """Yield ``(dotted-key, value)`` pairs so nested tables print one per line."""
    for key, value in data.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            yield from _flatten(value, f"{path}.")
        else:
            yield path, value


@app.command("show")
def show(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON."),
):
    """Show the config file, the context in use and its settings."""
    context = cfg.active(ctx)
    stored = cfg.table(context)
    data = {
        "file": str(context.file),
        "file_source": context.file_source,
        "context": context.name,
        "context_source": context.name_source,
        "url": context.url,
    }
    for key in ("aliases", "protected_attributes"):
        if key in stored:
            data[key] = stored[key]
    if output_json:
        typer.echo(json.dumps(data, indent=2))
        return
    for key, value in _flatten(data):
        typer.echo(f"{key} = {value}")


@app.command("contexts")
def list_contexts(ctx: typer.Context):
    """List the contexts of the config file and mark the default."""
    try:
        path, _ = cfg.config_file(cfg.choice(ctx)[0])
        found = cfg.contexts(cfg.read(path))
    except cfg.ConfigError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    for name, table in found.items():
        typer.echo(f"{name} (default)" if table.get("default") is True else name)
