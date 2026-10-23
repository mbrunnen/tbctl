"""ThingsBoard API keys that tbctl creates for itself, expire and rotate.

``tbctl auth login`` trades username and password for a short-lived JWT and
uses it once to create an API key that expires in 30 days. In the last 7 days
any command first creates a new key with the current one. The old key is not
deleted: it expires by itself, so tbctl processes still using it keep working.
"""

import base64
import binascii
import fcntl
import json
import socket
import sys
import time
from datetime import datetime
from typing import NamedTuple

import typer

import tbctl.config as cfg
import tbctl.credentials as credentials
from tbctl.commands import _client

DAY_MS = 24 * 3600 * 1000
KEY_LIFETIME_MS = 30 * DAY_MS
REFRESH_WINDOW_MS = 7 * DAY_MS
_PRE_VERIFICATION = "PRE_VERIFICATION_TOKEN"


class Key(NamedTuple):
    value: str
    id: str
    expires: int


class TwoFactorRequired(Exception):
    pass


def _now_ms() -> int:
    return int(time.time() * 1000)


def _jwt_scopes(token: str) -> list:
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError, binascii.Error):
        return []
    return claims.get("scopes") or []


def login(url: str, username: str, password: str) -> str:
    """Return a JWT for the user; raise TwoFactorRequired if the server asks for 2FA."""
    reply = _client.raw_post(
        _client.build_client(url),
        "/api/auth/login",
        {"username": username, "password": password},
    )
    token = reply["token"]
    if reply.get("scope") == _PRE_VERIFICATION or _PRE_VERIFICATION in _jwt_scopes(token):
        raise TwoFactorRequired()
    return token


def create(client, profile: str, now_ms: int) -> Key:
    user = _client.raw_get(client, "/api/auth/user")
    reply = _client.raw_post(
        client,
        "/api/apiKey",
        {
            "description": f"tbctl {socket.gethostname()} {profile}",
            "expirationTime": now_ms + KEY_LIFETIME_MS,
            "enabled": True,
            "userId": user["id"],
        },
    )
    return Key(reply["value"].removeprefix("ApiKey "), reply["id"]["id"], reply["expirationTime"])


def delete(client, key_id: str) -> None:
    _client.raw_delete(client, f"/api/apiKey/{key_id}")


def rotate(profile: str, force: bool = False) -> Key | None:
    """Replace the stored key with a new one, unless another process already did."""
    cfg.CONFIG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(cfg.CONFIG_DIR / f"{profile}.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        now = _now_ms()
        expires = credentials.expires(profile)
        if not force and expires is not None and expires - now >= REFRESH_WINDOW_MS:
            return None
        url = cfg.load(profile)["url"]
        key = create(_client.build_client(url, credentials.get(profile)), profile, now)
        insecure = credentials.source(profile) == "file"
        credentials.save(profile, key.value, key.id, key.expires, insecure=insecure)
        return key


def _describe(e: Exception) -> str:
    from tb_client.exceptions import ApiException

    if isinstance(e, ApiException):
        return f"Error {e.status}: {_client._error_detail(e)}"
    return str(e)


def ensure_fresh(profile: str) -> str | None:
    """Return the profile's key, rotating a stored one that is about to expire."""
    if credentials.source(profile) not in ("keyring", "file"):
        return credentials.get(profile)
    left = credentials.expires(profile) - _now_ms()
    if left <= 0:
        typer.echo(f"API key for profile '{profile}' expired. Run `tbctl auth login`.", err=True)
        raise typer.Exit(1)
    if left < REFRESH_WINDOW_MS:
        try:
            rotate(profile)
        except Exception as e:
            print(f"Warning: could not refresh the API key ({_describe(e)})", file=sys.stderr)
    return credentials.get(profile)


def date(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000).date().isoformat()
