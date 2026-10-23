"""The credential of each config profile: a JWT pair or an API key.

``TBCTL_TOKEN`` wins when it is set and is used as an API key: a container
usually has no Secret Service, so the variable is how a key gets in there.
Otherwise the secret comes from the Secret Service (KWallet, GNOME Keyring),
one entry per profile, or, where none is available, from the profile's TOML
file, which only the user can read. For a JWT login the secret is the JSON
pair of access and refresh token. The TOML always records the kind in ``auth``;
a secret without it counts as not logged in.
"""

import os
import sys
from typing import NamedTuple

import keyring
import keyring.errors

import tbctl.config as cfg

ENV = "TBCTL_TOKEN"
SERVICE = "tbctl"
JWT = "jwt"
API_KEY = "api-key"

_warned: set[str] = set()


class Credential(NamedTuple):
    kind: str
    secret: str
    source: str


def _keyring_get(profile: str) -> str | None:
    """Besides keyring's own errors, a locked wallet or a D-Bus error reply raises
    secretstorage and jeepney exceptions, so any failure counts as no secret, named once.
    """
    try:
        return keyring.get_password(SERVICE, profile)
    except Exception as e:
        if profile not in _warned:
            _warned.add(profile)
            print(
                f"Warning: cannot read the credential from the Secret Service ({e})",
                file=sys.stderr,
            )
        return None


def _warn_once(key: str, message: str) -> None:
    if key not in _warned and "_TBCTL_COMPLETE" not in os.environ:
        _warned.add(key)
        print(f"Warning: {message}", file=sys.stderr)


def load(profile: str) -> Credential | None:
    if os.environ.get(ENV):
        return Credential(API_KEY, os.environ[ENV], ENV)
    data = cfg.load(profile)
    kind = data.get("auth")
    if not kind:
        if _keyring_get(profile):
            _warn_once(
                f"{profile}:orphan",
                f"ignoring the credential in the Secret Service for profile '{profile}' "
                "without 'auth' in the profile file; run `tbctl auth login`",
            )
        return None
    if "token" in data:
        return Credential(kind, data["token"], "file")
    secret = _keyring_get(profile)
    if not secret:
        if profile not in _warned:
            _warn_once(
                f"{profile}:missing",
                f"no credential in the Secret Service for profile '{profile}'; "
                "run `tbctl auth login`",
            )
        return None
    return Credential(kind, secret, "keyring")


def save(
    profile: str,
    kind: str,
    secret: str,
    refresh_expires: int | None = None,
    insecure: bool = False,
) -> str:
    """Store a secret with its kind; return where the secret went."""
    data = cfg.load(profile)
    where = "file"
    reason = "--insecure-storage"
    if not insecure:
        try:
            keyring.set_password(SERVICE, profile, secret)
            where = "keyring"
        except Exception as e:
            reason = f"no Secret Service: {e}"
    if where == "file":
        path = cfg.CONFIG_DIR / f"{profile}.toml"
        print(f"Warning: storing the credential in {path} ({reason})", file=sys.stderr)
        data["token"] = secret
    else:
        data.pop("token", None)
    data["auth"] = kind
    if refresh_expires is None:
        data.pop("refresh_expires", None)
    else:
        data["refresh_expires"] = refresh_expires
    cfg.save(data, profile)
    return where


def clear(profile: str) -> bool:
    """Remove the profile's credential; return whether there was one."""
    removed = False
    try:
        keyring.delete_password(SERVICE, profile)
        removed = True
    except keyring.errors.PasswordDeleteError:
        pass
    except Exception as e:
        print(
            f"Warning: cannot remove the credential from the Secret Service ({e})",
            file=sys.stderr,
        )
    if not (cfg.CONFIG_DIR / f"{profile}.toml").exists():
        return removed
    data = cfg.load(profile)
    for key in ("token", "auth", "refresh_expires", "customer_id"):
        if data.pop(key, None) is not None:
            removed = True
    cfg.save(data, profile)
    return removed
