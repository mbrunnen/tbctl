import json
import os
import sys
from urllib.parse import urlparse

import typer

import tbctl.config as cfg
import tbctl.credentials as credentials
from tbctl import session, state
from tbctl.commands import _client
from tbctl.commands._client import _error_detail, build_client, check_connection

app = typer.Typer(no_args_is_help=True, help="Log in to ThingsBoard.")


def _stdin_is_tty() -> bool:
    return sys.stdin.isatty()


def _fail(message: str) -> None:
    typer.echo(message, err=True)
    raise typer.Exit(1)


def _not_logged_in(context: cfg.Context) -> None:
    _fail(f"Not logged in for context '{context.name}'. Run `tbctl auth login`.")


def _api_error(e: Exception, url: str) -> None:
    from tb_client.exceptions import ApiException

    if isinstance(e, ApiException):
        _fail(f"Error {e.status}: {_error_detail(e)}")
    _fail(f"Could not reach {url}: {e}")


def _whoami(url: str, token: str, prefix: str, what: str) -> dict:
    from tb_client.exceptions import ApiException

    try:
        return _client.raw_get(build_client(url, token, prefix), "/api/auth/user")
    except ApiException as e:
        _fail(f"The server rejected the {what}: Error {e.status}: {_error_detail(e)}")
    except Exception as e:
        _fail(f"Could not reach {url}: {e}")


def _customer_id(user: dict) -> str | None:
    """A customer user may only use the customer endpoints, so remember whose."""
    if user.get("authority") == "CUSTOMER_USER":
        return user["customerId"]["id"]
    return None


def _mismatch(context: cfg.Context, key: str, value: str) -> None:
    _fail(f"Context '{context.name}' has {key} = \"{value}\"; edit {context.file} to change it.")


def _login_context(ctx, url_flag: str | None, quiet: bool) -> tuple[cfg.Context, bool]:
    """Return the context to log in to, and whether it is new.

    A context missing from the file, or the first one of an empty file, is
    asked for and written only after the login succeeds.
    """
    config_flag, context_flag = cfg.choice(ctx)
    try:
        path, file_source = cfg.config_file(config_flag)
        found = cfg.contexts(cfg.read(path))
    except cfg.ConfigError as e:
        _fail(f"Error: {e}")
    name = context_flag or os.environ.get(cfg.CONTEXT_ENV)
    derived = None
    if url_flag and not name:
        wanted = cfg.normalise_url(url_flag)
        same = [
            n for n, t in found.items() if t.get("url") and cfg.normalise_url(t["url"]) == wanted
        ]
        name = derived = same[0] if same else urlparse(wanted).hostname
    if (name and name in found) or (not name and found):
        try:
            context = cfg.resolve(config_flag, derived) if derived else cfg.active(ctx)
        except cfg.ConfigError as e:
            _fail(f"Error: {e}")
        if url_flag and cfg.normalise_url(url_flag) != context.url:
            _mismatch(context, "url", context.url)
        return context, False
    if not url_flag and quiet:
        _fail("Pass --url: the context is new and --password-stdin asks for nothing.")
    url = cfg.normalise_url(url_flag or typer.prompt("ThingsBoard URL"))
    name = name or urlparse(url).hostname
    if not name:
        _fail(f"Cannot name a context after '{url}'; give the URL with https://.")
    return cfg.Context(path, file_source, name, "new", url), True


def _add_user(context: cfg.Context, username: str) -> None:
    """Record the user a context logs in as; the config file stays its only source."""
    doc = cfg.read(context.file)
    doc["contexts"][context.name]["user"] = username
    cfg.write(context.file, doc)
    typer.echo(f"Added user = \"{username}\" to context '{context.name}' in {context.file}.")


def _store(
    context: cfg.Context, kind: str, secret: str, expires, insecure: bool, user: dict
) -> None:
    """Replace the context's login, so no state of an old login survives."""
    credentials.clear(context)
    customer_id = _customer_id(user)
    if customer_id:
        state.save(context.key, {"customer_id": customer_id})
    credentials.save(context, kind, secret, expires, insecure=insecure)


def _renewed(context: cfg.Context) -> bool:
    """Renew a stored session, so a valid one needs no password."""
    cred = credentials.load(context)
    if cred is None or cred.kind != credentials.JWT:
        return False
    try:
        pair = session.renew(context, force=True)
    except session.SessionExpired:
        return False
    except Exception as e:
        _api_error(e, context.url)
    expires = session.date(session.exp_ms(pair["refreshToken"]))
    typer.echo(f"Already logged in to {context.url}; session renewed, valid until {expires}.")
    return True


@app.command("login")
def login(
    ctx: typer.Context,
    api_key: bool = typer.Option(
        False, "--api-key", help="Store an API key (prompted, or read from stdin) instead."
    ),
    insecure_storage: bool = typer.Option(
        False, "--insecure-storage", help="Store the credential in the state file."
    ),
    url: str | None = typer.Option(
        None, "--url", help="The URL of a context that is not in the config file yet."
    ),
    user: str | None = typer.Option(
        None, "--user", help="The user of a context that has none yet."
    ),
    password_stdin: bool = typer.Option(
        False, "--password-stdin", help="Read the password from the first line of stdin."
    ),
):
    """Log in as the context's user with a password, or store an API key.

    A stored session that can still be renewed is renewed instead.
    """
    if os.environ.get(credentials.ENV):
        _fail(f"{credentials.ENV} is set; unset it to log in.")
    if api_key and (user or password_stdin):
        _fail("--user and --password-stdin cannot be used with --api-key.")
    context, new_context = _login_context(ctx, url, password_stdin)
    url = context.url
    username = None if new_context else cfg.table(context).get("user")
    if user and username and user != username:
        _mismatch(context, "user", username)

    if api_key:
        if _stdin_is_tty():
            key = typer.prompt("API key", hide_input=True)
        else:
            key = sys.stdin.read().strip()
        user = _whoami(url, key, "ApiKey", "API key")
        if new_context:
            cfg.add_context(context.file, context.name, url)
        _store(context, credentials.API_KEY, key, None, insecure_storage, user)
        typer.echo(f"Logged in to {url} as {user.get('email')} with an API key.")
        return

    if not new_context and _renewed(context):
        return
    new_user = not username
    username = username or user
    if not username and password_stdin:
        _fail("Pass --user: the context has no user and --password-stdin asks for nothing.")
    if not username:
        username = typer.prompt("Username")
    if password_stdin:
        password = sys.stdin.readline().rstrip("\n")
        if not password:
            _fail("No password on stdin.")
    else:
        password = typer.prompt("Password", hide_input=True)
    try:
        pair = session.login(url, username, password)
    except session.TwoFactorRequired:
        _fail("Two-factor authentication is not supported.")
    except session.UnexpectedReply as e:
        _fail(f"Login failed: {e}")
    except Exception as e:
        _api_error(e, url)
    user = _whoami(url, pair["token"], "Bearer", "session")
    expires = session.exp_ms(pair["refreshToken"])
    _store(context, credentials.JWT, json.dumps(pair), expires, insecure_storage, user)
    if new_context:
        cfg.add_context(context.file, context.name, url, username)
        typer.echo(f"Added context '{context.name}' to {context.file}.")
    elif new_user:
        _add_user(context, username)
    typer.echo(f"Logged in to {url} as {username}; session valid until {session.date(expires)}.")


@app.command("refresh")
def refresh(ctx: typer.Context):
    """Renew the session now."""
    context = cfg.active(ctx)
    cred = credentials.load(context)
    if cred is None:
        _not_logged_in(context)
    if cred.kind != credentials.JWT:
        _fail("API keys are not refreshed.")
    try:
        pair = session.renew(context, force=True)
    except session.SessionExpired as e:
        _fail(f"Session for context '{context.name}' {e}. Run `tbctl auth login`.")
    except Exception as e:
        _api_error(e, context.url)
    typer.echo(
        f"Session renewed; valid until {session.date(session.exp_ms(pair['refreshToken']))}."
    )


@app.command("status")
def status(
    ctx: typer.Context,
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON."),
):
    """Show who is logged in, how, and until when."""
    context = cfg.active(ctx)
    cred = credentials.load(context)
    if not cred:
        _not_logged_in(context)
    token, prefix = session.ensure_fresh(context)
    ok, user = check_connection(context.url, token, prefix)
    data = {"user": user, "auth": cred.kind, "source": cred.source}
    if cred.kind == credentials.JWT:
        expires = state.load(context.key).get("refresh_expires")
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
    context = cfg.active(ctx)
    if "auth" not in state.load(context.key):
        if credentials.clear(context):
            typer.echo(f"Removed a credential without a login from context '{context.name}'.")
            return
        _not_logged_in(context)
    cred = credentials.load(context)
    if cred is None:
        print("Warning: the stored credential cannot be read; nothing sent.", file=sys.stderr)
    elif cred.source == credentials.ENV:
        print(f"Warning: {credentials.ENV} is set; nothing sent to the server.", file=sys.stderr)
    elif cred.kind == credentials.JWT:
        try:
            session.logout(context.url, json.loads(cred.secret))
        except Exception as e:
            print(f"Warning: could not end the session on the server ({e})", file=sys.stderr)
    credentials.clear(context)
    typer.echo(f"Logged out of context '{context.name}'.")
