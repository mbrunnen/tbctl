import typer

import tbctl.config as cfg
from tbctl.commands._client import check_connection

app = typer.Typer(no_args_is_help=True, help="Manage CLI configuration.")


def _flatten(data: dict, prefix: str = ""):
    """Yield ``(dotted-key, value)`` pairs so nested tables print one per line."""
    for key, value in data.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            yield from _flatten(value, f"{path}.")
        else:
            yield path, value


@app.command("init")
def init(ctx: typer.Context):
    """Interactively set the URL and token, verifying them against the server."""
    profile = ctx.obj["profile"]
    data = cfg.load(profile)

    existing_url = data.get("url")
    if existing_url:
        url = typer.prompt("ThingsBoard URL", default=existing_url)
    else:
        url = typer.prompt("ThingsBoard URL")

    existing_token = data.get("token")
    if existing_token:
        token = (
            typer.prompt(
                "API token (press Enter to keep existing)",
                hide_input=True,
                default="",
                show_default=False,
            )
            or existing_token
        )
    else:
        token = typer.prompt("API token", hide_input=True)

    ok, message = check_connection(url, token)
    if ok:
        typer.echo(f"Connection OK (logged in as {message})")
    else:
        typer.echo(f"Warning: could not verify credentials: {message}")

    data["url"] = url
    data["token"] = token
    cfg.save(data, profile)
    typer.echo(f"Configuration saved for profile '{profile}'.")


@app.command("set-url")
def set_url(ctx: typer.Context, url: str = typer.Argument(help="ThingsBoard base URL.")):
    profile = ctx.obj["profile"]
    data = cfg.load(profile)
    data["url"] = url
    cfg.save(data, profile)
    typer.echo(f"URL set to {url}")


@app.command("set-token")
def set_token(ctx: typer.Context, token: str = typer.Argument(help="API token.")):
    profile = ctx.obj["profile"]
    data = cfg.load(profile)
    data["token"] = token
    cfg.save(data, profile)
    typer.echo("Token saved.")


@app.command("show")
def show(ctx: typer.Context):
    profile = ctx.obj["profile"]
    data = cfg.load(profile)
    if not data:
        typer.echo(f"No configuration found for profile '{profile}'.")
        return
    for key, value in _flatten(data):
        typer.echo(f"{key} = {value}")
