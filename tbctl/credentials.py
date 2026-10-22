"""The API token of each config profile.

``TBCTL_TOKEN`` wins when it is set: a container usually has no Secret Service,
so the variable is how the token gets in there. Otherwise the token comes from
the Secret Service (KWallet, GNOME Keyring), one entry per profile. It is never
written to the profile's TOML file.
"""

import os

import keyring

ENV = "TBCTL_TOKEN"
SERVICE = "tbctl"


def stored(profile: str) -> str | None:
    """Return the profile's token from the Secret Service, or None if it cannot be read.

    Besides keyring's own errors, a locked wallet or a D-Bus error reply raises
    secretstorage and jeepney exceptions, so any failure counts as no token.
    """
    try:
        return keyring.get_password(SERVICE, profile)
    except Exception:
        return None


def get(profile: str) -> str | None:
    return os.environ.get(ENV) or stored(profile)


def store(profile: str, token: str) -> None:
    keyring.set_password(SERVICE, profile, token)
