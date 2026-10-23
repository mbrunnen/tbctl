import json
import os
import sys

import typer

import tbctl.config as cfg
import tbctl.credentials as credentials
from tbctl import session
from tbctl.commands._client import _error_detail, check_connection

app = typer.Typer(no_args_is_help=True, help="Log in to ThingsBoard.")


def _stdin_is_tty() -> bool:
    return sys.stdin.isatty()


def _fail(message: str) -> None:
    typer.echo(message, err=True)
    raise typer.Exit(1)


def _not_logged_in(profile: str) -> None:
    _fail(f"Not logged in for profile '{profile}'. Run `tbctl auth login`.")


def _api_error(e: Exception, url: str) -> None:
    from tb_client.exceptions import ApiException

    if isinstance(e, ApiException):
        _fail(f"Error {e.status}: {_error_detail(e)}")
    _fail(f"Could not reach {url}: {e}")


def _store(profile: str, url: str, kind: str, secret: str, expires, insecure: bool) -> None:
    """Replace the profile's login, so an old secret is never paired with a new URL."""
    credentials.clear(profile)
    data = cfg.load(profile)
    data["url"] = url
    cfg.save(data, profile)
    credentials.save(profile, kind, secret, expires, insecure=insecure)


@app.command("login")
def login(
    ctx: typer.Context,
    url: str = typer.Option(None, "--url", help="ThingsBoard base URL."),
    username: str = typer.Option(None, "--username", "-u", help="User email."),
    api_key: bool = typer.Option(
        False, "--api-key", help="Store an API key (prompted, or read from stdin) instead."
    ),
    insecure_storage: bool = typer.Option(
        False, "--insecure-storage", help="Store the credential in the profile file."
    ),
):
    """Log in with username and password, or store an API key."""
    profile = ctx.obj["profile"]
    if os.environ.get(credentials.ENV):
        _fail(f"{credentials.ENV} is set; unset it to log in.")
    if api_key and username:
        _fail("--api-key and --username exclude each other.")
    if not url:
        url = typer.prompt("ThingsBoard URL", default=cfg.load(profile).get("url"))

    if api_key:
        if _stdin_is_tty():
            key = typer.prompt("API key", hide_input=True)
        else:
            key = sys.stdin.read().strip()
        ok, user = check_connection(url, key)
        if not ok:
            _fail(f"The server rejected the API key: {user}")
        _store(profile, url, credentials.API_KEY, key, None, insecure_storage)
        typer.echo(f"Logged in to {url} as {user} with an API key.")
        return

    if not username:
        username = typer.prompt("Username")
    password = typer.prompt("Password", hide_input=True)
    try:
        pair = session.login(url, username, password)
    except session.TwoFactorRequired:
        _fail("Two-factor authentication is not supported.")
    except session.UnexpectedReply as e:
        _fail(f"Login failed: {e}")
    except Exception as e:
        _api_error(e, url)
    expires = session.exp_ms(pair["refreshToken"])
    _store(profile, url, credentials.JWT, json.dumps(pair), expires, insecure_storage)
    typer.echo(f"Logged in to {url} as {username}; session valid until {session.date(expires)}.")


@app.command("refresh")
def refresh(ctx: typer.Context):
    """Renew the session now."""
    profile = ctx.obj["profile"]
    cred = credentials.load(profile)
    if cred is None:
        _not_logged_in(profile)
    if cred.kind != credentials.JWT:
        _fail("API keys are not refreshed.")
    try:
        pair = session.renew(profile, force=True)
    except session.SessionExpired as e:
        _fail(f"Session for profile '{profile}' {e}. Run `tbctl auth login`.")
    except Exception as e:
        _api_error(e, cfg.load(profile).get("url") or "the server")
    typer.echo(
        f"Session renewed; valid until {session.date(session.exp_ms(pair['refreshToken']))}."
    )


@app.command("status")
def status(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON."),
):
    """Show who is logged in, how, and until when."""
    profile = ctx.obj["profile"]
    url = cfg.load(profile).get("url")
    if not url or not credentials.load(profile):
        _not_logged_in(profile)
    cred = credentials.load(profile)
    token, prefix = session.ensure_fresh(profile)
    ok, user = check_connection(url, token, prefix)
    data = {"url": url, "user": user, "auth": cred.kind, "source": cred.source}
    if cred.kind == credentials.JWT:
        expires = cfg.load(profile).get("refresh_expires")
        data["expires"] = session.date(expires) if expires else "unknown"
    if output_json:
        typer.echo(json.dumps(data, indent=2))
    else:
        for key, value in data.items():
            typer.echo(f"{key} = {value}")
    if not ok:
        _fail(f"The server rejected the credential: {user}")


@app.command("logout")
def logout(ctx: typer.Context):
    """End the session on the server and forget the credential locally."""
    profile = ctx.obj["profile"]
    data = cfg.load(profile)
    if "auth" not in data:
        if credentials.clear(profile):
            typer.echo(f"Removed a credential without 'auth' from profile '{profile}'.")
            return
        _not_logged_in(profile)
    cred = credentials.load(profile)
    if cred is None:
        print("Warning: the stored credential cannot be read; nothing sent.", file=sys.stderr)
    elif cred.source == credentials.ENV:
        print(f"Warning: {credentials.ENV} is set; nothing sent to the server.", file=sys.stderr)
    elif cred.kind == credentials.JWT:
        try:
            session.logout(data["url"], json.loads(cred.secret))
        except Exception as e:
            print(f"Warning: could not end the session on the server ({e})", file=sys.stderr)
    credentials.clear(profile)
    typer.echo(f"Logged out of profile '{profile}'.")
