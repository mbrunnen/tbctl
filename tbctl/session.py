"""The ThingsBoard session behind ``tbctl auth login``.

Login trades username and password for a JWT pair. The access token lives a
few hours, the refresh token days (both set by the server). Before every
command a JWT access token that expires within a minute is renewed with the
refresh token, under a per-context lock so parallel runs renew once. An API
key, from ``TBCTL_TOKEN`` or ``auth login --api-key``, is used as it is.
"""

import base64
import binascii
import fcntl
import json
import sys
import time
from datetime import datetime

import typer

import tbctl.credentials as credentials
from tbctl import state
from tbctl.commands import _client
from tbctl.config import Context

RENEW_WINDOW_MS = 60_000
_PRE_VERIFICATION = "PRE_VERIFICATION_TOKEN"


class TwoFactorRequired(Exception):
    pass


class UnexpectedReply(Exception):
    def __init__(self, path: str):
        super().__init__(f"unexpected reply from {path}")


def _pair(reply, path: str) -> dict:
    if not isinstance(reply, dict) or not reply.get("token") or not reply.get("refreshToken"):
        raise UnexpectedReply(path)
    return {"token": reply["token"], "refreshToken": reply["refreshToken"]}


class SessionExpired(Exception):
    def __init__(self, reason: str = "expired"):
        super().__init__(reason)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _claims(token: str) -> dict:
    try:
        payload = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError, binascii.Error):
        return {}


def exp_ms(token: str) -> int:
    return int(_claims(token).get("exp", 0)) * 1000


def date(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000).isoformat(" ", "minutes")


def login(url: str, username: str, password: str) -> dict:
    """Return the JWT pair; raise TwoFactorRequired if the server asks for 2FA."""
    reply = _client.raw_post(
        _client.build_client(url),
        "/api/auth/login",
        {"username": username, "password": password},
    )
    if isinstance(reply, dict) and reply.get("token"):
        scopes = _claims(reply["token"]).get("scopes") or []
        if reply.get("scope") == _PRE_VERIFICATION or _PRE_VERIFICATION in scopes:
            raise TwoFactorRequired()
    return _pair(reply, "/api/auth/login")


def logout(url: str, pair: dict) -> None:
    _client.raw_post(
        _client.build_client(url, pair["token"], prefix="Bearer"), "/api/auth/logout", {}
    )


def _stored_pair(context: Context) -> tuple[dict, str]:
    cred = credentials.load(context)
    if cred is None:
        raise SessionExpired("cannot be read")
    try:
        pair = json.loads(cred.secret)
        return {"token": pair["token"], "refreshToken": pair["refreshToken"]}, cred.source
    except (ValueError, TypeError, KeyError) as e:
        raise SessionExpired("cannot be read") from e


def renew(context: Context, force: bool = False) -> dict | None:
    """Renew the stored pair, unless it is still fresh or another process renewed it."""
    from tb_client.exceptions import ApiException

    with open(state.lock_path(context.safe_key), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        pair, source = _stored_pair(context)
        now = _now_ms()
        if not force and exp_ms(pair["token"]) - now >= RENEW_WINDOW_MS:
            return None
        if exp_ms(pair["refreshToken"]) <= now:
            raise SessionExpired()
        try:
            reply = _client.raw_post(
                _client.build_client(context.url),
                "/api/auth/token",
                {"refreshToken": pair["refreshToken"]},
            )
        except ApiException as e:
            if e.status == 401:
                raise SessionExpired() from e
            raise
        new = _pair(reply, "/api/auth/token")
        credentials.save(
            context,
            credentials.JWT,
            json.dumps(new),
            exp_ms(new["refreshToken"]),
            insecure=source == "file",
        )
        return new


def _describe(e: Exception) -> str:
    from tb_client.exceptions import ApiException

    if isinstance(e, ApiException):
        return f"Error {e.status}: {_client._error_detail(e)}"
    return str(e)


def ensure_fresh(context: Context) -> tuple[str, str] | None:
    """Return the token to send and its header prefix, renewing a JWT about to expire."""
    cred = credentials.load(context)
    if cred is None:
        return None
    if cred.kind != credentials.JWT:
        return cred.secret, "ApiKey"
    try:
        try:
            renew(context)
        except SessionExpired:
            raise
        except Exception as e:
            pair, _ = _stored_pair(context)
            if exp_ms(pair["token"]) <= _now_ms():
                typer.echo(f"Could not renew the session ({_describe(e)}).", err=True)
                raise typer.Exit(1)
            print(f"Warning: could not renew the session ({_describe(e)})", file=sys.stderr)
        pair, _ = _stored_pair(context)
    except SessionExpired as e:
        typer.echo(f"Session for context '{context.name}' {e}. Run `tbctl auth login`.", err=True)
        raise typer.Exit(1)
    return pair["token"], "Bearer"
