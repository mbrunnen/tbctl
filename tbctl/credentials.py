"""The credential of each context: a JWT pair or an API key.

``TBCTL_TOKEN`` wins when it is set and is used as an API key: a container
usually has no Secret Service, so the variable is how a key gets in there.
Otherwise the secret comes from the Secret Service (KWallet, GNOME Keyring),
one entry per context key, or, where none is available, from the state file,
which only the user can read. For a JWT login the secret is the JSON pair of
access and refresh token. The state always records the kind in ``auth``; a
secret without it counts as not logged in.
"""

import os
import sys
from typing import NamedTuple

import keyring
import keyring.errors

from tbctl import state
from tbctl.config import Context

ENV = "TBCTL_TOKEN"
SERVICE = "tbctl"
JWT = "jwt"
API_KEY = "api-key"

_warned: set[str] = set()


class Credential(NamedTuple):
    kind: str
    secret: str
    source: str


def _keyring_get(key: str) -> str | None:
    """Besides keyring's own errors, a locked wallet or a D-Bus error reply raises
    secretstorage and jeepney exceptions, so any failure counts as no secret, named once.
    """
    try:
        return keyring.get_password(SERVICE, key)
    except Exception as e:
        if key not in _warned:
            _warned.add(key)
            print(
                f"Warning: cannot read the credential from the Secret Service ({e})",
                file=sys.stderr,
            )
        return None


def _warn_once(key: str, message: str) -> None:
    if key not in _warned and "_TBCTL_COMPLETE" not in os.environ:
        _warned.add(key)
        print(f"Warning: {message}", file=sys.stderr)


def load(context: Context) -> Credential | None:
    if os.environ.get(ENV):
        return Credential(API_KEY, os.environ[ENV], ENV)
    data = state.load(context.key)
    kind = data.get("auth")
    if not kind:
        if _keyring_get(context.key):
            _warn_once(
                f"{context.key}:orphan",
                f"ignoring the credential in the Secret Service for context '{context.name}' "
                "without a login in the state file; run `tbctl auth login`",
            )
        return None
    if "token" in data:
        return Credential(kind, data["token"], "file")
    secret = _keyring_get(context.key)
    if not secret:
        _warn_once(
            f"{context.key}:missing",
            f"no credential in the Secret Service for context '{context.name}'; "
            "run `tbctl auth login`",
        )
        return None
    return Credential(kind, secret, "keyring")


def save(
    context: Context,
    kind: str,
    secret: str,
    refresh_expires: int | None = None,
    insecure: bool = False,
) -> str:
    """Store a secret with its kind; return where the secret went."""
    data = state.load(context.key)
    where = "file"
    reason = "--insecure-storage"
    if not insecure:
        try:
            keyring.set_password(SERVICE, context.key, secret)
            where = "keyring"
        except Exception as e:
            reason = f"no Secret Service: {e}"
    if where == "file":
        path = state.STATE_DIR / "state.toml"
        print(f"Warning: storing the credential in {path} ({reason})", file=sys.stderr)
        data["token"] = secret
    else:
        data.pop("token", None)
    data["auth"] = kind
    if refresh_expires is None:
        data.pop("refresh_expires", None)
    else:
        data["refresh_expires"] = refresh_expires
    state.save(context.key, data)
    return where


def clear(context: Context) -> bool:
    """Remove the context's credential and login state; return whether there was one."""
    removed = False
    try:
        keyring.delete_password(SERVICE, context.key)
        removed = True
    except keyring.errors.PasswordDeleteError:
        pass
    except Exception as e:
        print(
            f"Warning: cannot remove the credential from the Secret Service ({e})",
            file=sys.stderr,
        )
    if state.load(context.key):
        removed = True
        state.save(context.key, {})
    return removed
