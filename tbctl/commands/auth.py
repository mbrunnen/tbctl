import json
import os
import sys

import typer

import tbctl.config as cfg
import tbctl.credentials as credentials
from tbctl import apikey
from tbctl.commands._client import (
    _error_detail,
    build_client,
    check_connection,
    handle_api_error,
)

app = typer.Typer(no_args_is_help=True, help="Log in to ThingsBoard and manage the API key.")


def _refuse_env(message: str) -> None:
    if os.environ.get(credentials.ENV):
        typer.echo(message, err=True)
        raise typer.Exit(1)


def _not_logged_in(profile: str) -> None:
    typer.echo(f"Not logged in for profile '{profile}'. Run `tbctl auth login`.", err=True)
    raise typer.Exit(1)


@app.command("login")
def login(
    ctx: typer.Context,
    url: str = typer.Option(None, "--url", help="ThingsBoard base URL."),
    username: str = typer.Option(None, "--username", "-u", help="User email."),
    insecure_storage: bool = typer.Option(
        False, "--insecure-storage", help="Store the API key in the profile file, not the keyring."
    ),
):
    """Log in with username and password and store a new 30-day API key."""
    profile = ctx.obj["profile"]
    _refuse_env(f"{credentials.ENV} is set; unset it to log in.")
    data = cfg.load(profile)
    if not url:
        url = typer.prompt("ThingsBoard URL", default=data.get("url"))
    if not username:
        username = typer.prompt("Username")
    password = typer.prompt("Password", hide_input=True)

    try:
        jwt = apikey.login(url, username, password)
        key = apikey.create(build_client(url, jwt, prefix="Bearer"), profile, apikey._now_ms())
    except apikey.TwoFactorRequired:
        typer.echo("Two-factor authentication is not supported.", err=True)
        raise typer.Exit(1)
    except Exception as e:
        from tb_client.exceptions import ApiException

        if isinstance(e, ApiException):
            typer.echo(f"Error {e.status}: {_error_detail(e)}", err=True)
            raise typer.Exit(1)
        typer.echo(f"Could not reach {url}: {e}", err=True)
        raise typer.Exit(1)

    credentials.clear(profile)
    data = cfg.load(profile)
    data["url"] = url
    cfg.save(data, profile)
    credentials.save(profile, key.value, key.id, key.expires, insecure=insecure_storage)
    typer.echo(f"Logged in to {url} as {username}; API key expires {apikey.date(key.expires)}.")


@app.command("refresh")
def refresh(ctx: typer.Context):
    """Replace the API key with a new 30-day one now."""
    profile = ctx.obj["profile"]
    _refuse_env(f"{credentials.ENV} is set; tbctl does not refresh it.")
    expires = credentials.expires(profile)
    if not credentials.source(profile):
        _not_logged_in(profile)
    if expires <= apikey._now_ms():
        typer.echo(f"API key for profile '{profile}' expired. Run `tbctl auth login`.", err=True)
        raise typer.Exit(1)
    try:
        key = apikey.rotate(profile, force=True)
    except Exception as e:
        handle_api_error(e)
    typer.echo(f"API key renewed; it expires {apikey.date(key.expires)}.")


@app.command("status")
def status(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON."),
):
    """Show who is logged in, where the key comes from and when it expires."""
    profile = ctx.obj["profile"]
    url = cfg.load(profile).get("url")
    source = credentials.source(profile)
    if not url or not source:
        _not_logged_in(profile)
    ok, user = check_connection(url, credentials.get(profile))
    data = {"url": url, "user": user, "token": source}
    expires = credentials.expires(profile)
    if source != credentials.ENV and expires is not None:
        data["expires"] = apikey.date(expires)
    if output_json:
        typer.echo(json.dumps(data, indent=2))
    else:
        for key, value in data.items():
            typer.echo(f"{key} = {value}")
    if not ok:
        typer.echo(f"The server rejected the API key: {user}", err=True)
        raise typer.Exit(1)


@app.command("logout")
def logout(ctx: typer.Context):
    """Delete the API key on the server and forget it locally."""
    profile = ctx.obj["profile"]
    key_id = cfg.load(profile).get("token_id")
    if not key_id:
        _not_logged_in(profile)
    source = credentials.source(profile)
    if source in ("keyring", "file"):
        try:
            token = credentials.get(profile)
            apikey.delete(build_client(cfg.load(profile)["url"], token), key_id)
        except Exception as e:
            print(f"Warning: could not delete the API key on the server ({e})", file=sys.stderr)
    else:
        reason = f"{credentials.ENV} is set" if source else "the stored key cannot be read"
        print(
            f"Warning: the API key was not deleted on the server ({reason}); it expires by itself.",
            file=sys.stderr,
        )
    credentials.clear(profile)
    typer.echo(f"Logged out of profile '{profile}'.")
