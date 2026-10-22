import json
import os

import typer

import tbctl.config as cfg
import tbctl.credentials as credentials
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


def _store_token(profile: str, token: str) -> None:
    try:
        credentials.store(profile, token)
    except Exception as e:
        typer.echo(
            f"Could not store the token in the Secret Service ({e}). "
            f"Set {credentials.ENV} instead.",
            err=True,
        )
        raise typer.Exit(1)


def _token_source(profile: str) -> str:
    if os.environ.get(credentials.ENV):
        return credentials.ENV
    if credentials.stored(profile):
        return "keyring"
    return "not set"


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

    existing_token = credentials.stored(profile)
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

    _store_token(profile, token)
    data["url"] = url
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
    _store_token(ctx.obj["profile"], token)
    typer.echo("Token saved.")


@app.command("show")
def show(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON."),
):
    profile = ctx.obj["profile"]
    data = {key: value for key, value in cfg.load(profile).items() if key in cfg.KEYS}
    source = _token_source(profile)
    if not data and source == "not set":
        typer.echo("{}" if output_json else f"No configuration found for profile '{profile}'.")
        return
    data["token"] = source
    if output_json:
        typer.echo(json.dumps(data, indent=2))
        return
    for key, value in _flatten(data):
        typer.echo(f"{key} = {value}")
