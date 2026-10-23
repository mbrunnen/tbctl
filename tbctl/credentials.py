"""The API key of each config profile.

``TBCTL_TOKEN`` wins when it is set: a container usually has no Secret Service,
so the variable is how a key gets in there, and tbctl never rotates it.
Otherwise the key comes from the Secret Service (KWallet, GNOME Keyring), one
entry per profile, or, where none is available, from the profile's TOML file,
which only the user can read. The key's id and expiry always live in the TOML;
a stored key without an id counts as not logged in.
"""

import os
import sys

import keyring
import keyring.errors

import tbctl.config as cfg

ENV = "TBCTL_TOKEN"
SERVICE = "tbctl"


_warned: set[str] = set()


def _keyring_get(profile: str) -> str | None:
    """Besides keyring's own errors, a locked wallet or a D-Bus error reply raises
    secretstorage and jeepney exceptions, so any failure counts as no key, named once.
    """
    try:
        return keyring.get_password(SERVICE, profile)
    except Exception as e:
        if profile not in _warned:
            _warned.add(profile)
            print(
                f"Warning: cannot read the API key from the Secret Service ({e})", file=sys.stderr
            )
        return None


def _stored(profile: str) -> tuple[str | None, str | None]:
    data = cfg.load(profile)
    if "token_id" not in data or "token_expires" not in data:
        return None, None
    if "token" in data:
        return data["token"], "file"
    value = _keyring_get(profile)
    return (value, "keyring") if value else (None, None)


def get(profile: str) -> str | None:
    return os.environ.get(ENV) or _stored(profile)[0]


def source(profile: str) -> str | None:
    if os.environ.get(ENV):
        return ENV
    return _stored(profile)[1]


def expires(profile: str) -> int | None:
    return cfg.load(profile).get("token_expires")


def save(profile: str, value: str, key_id: str, expires: int, insecure: bool = False) -> str:
    """Store a key with its id and expiry; return where the value went."""
    data = cfg.load(profile)
    where = "file"
    reason = "--insecure-storage"
    if not insecure:
        try:
            keyring.set_password(SERVICE, profile, value)
            where = "keyring"
        except Exception as e:
            reason = f"no Secret Service: {e}"
    if where == "file":
        path = cfg.CONFIG_DIR / f"{profile}.toml"
        print(f"Warning: storing the API key in {path} ({reason})", file=sys.stderr)
        data["token"] = value
    else:
        data.pop("token", None)
    data["token_id"] = key_id
    data["token_expires"] = expires
    cfg.save(data, profile)
    return where


def clear(profile: str) -> None:
    try:
        keyring.delete_password(SERVICE, profile)
    except keyring.errors.PasswordDeleteError:
        pass
    except Exception as e:
        print(f"Warning: cannot remove the API key from the Secret Service ({e})", file=sys.stderr)
    if not (cfg.CONFIG_DIR / f"{profile}.toml").exists():
        return
    data = cfg.load(profile)
    for key in ("token", "token_id", "token_expires"):
        data.pop(key, None)
    cfg.save(data, profile)
