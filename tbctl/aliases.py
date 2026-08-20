"""Local device aliases, stored per config profile.

An alias maps a free-text name to a device: the device's ThingsBoard name and,
optionally, its UUID. ``tbctl telemetry latest ruedi`` then works in place of
the device's own name, and a stored UUID lets that resolve without the
name lookup, which needs tenant device-read permission. Aliases live in the
profile's own config file and never touch the server.
"""

import re
from typing import NamedTuple

import tbctl.config as cfg

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


class Alias(NamedTuple):
    """The device an alias points at: its name, plus its UUID when known."""

    name: str
    id: str | None = None


def _entry(value) -> Alias:
    """Read one stored alias, accepting the older plain-string form."""
    if isinstance(value, str):
        return Alias(value)
    return Alias(value["name"], value.get("id"))


def _stored(alias: Alias) -> dict[str, str]:
    """Render an alias for TOML, which has no way to store a missing UUID."""
    stored = {"name": alias.name}
    if alias.id:
        stored["id"] = alias.id
    return stored


def _table(data: dict) -> dict[str, Alias]:
    return {name: _entry(value) for name, value in data.get("aliases", {}).items()}


def load(profile: str = "default") -> dict[str, Alias]:
    """Return the profile's aliases, migrating older string entries on the way.

    A migration writes the converted table back once, so every later read and
    every other tbctl version sees a single format.
    """
    data = cfg.load(profile)
    table = _table(data)
    if any(isinstance(value, str) for value in data.get("aliases", {}).values()):
        _save(data, table, profile)
    return table


def _save(data: dict, table: dict[str, Alias], profile: str) -> None:
    data["aliases"] = {name: _stored(alias) for name, alias in table.items()}
    cfg.save(data, profile)


def _stored_key(table: dict[str, Alias], name: str) -> str | None:
    """Return the stored key matching ``name`` case-insensitively."""
    folded = name.casefold()
    for key in table:
        if key.casefold() == folded:
            return key
    return None


def resolve(profile: str, name: str) -> Alias | None:
    table = load(profile)
    key = _stored_key(table, name)
    return table[key] if key else None


def add(profile: str, name: str, device: str, device_id: str | None = None) -> Alias | None:
    """Point ``name`` at a device, returning the entry it replaced.

    The entry is replaced whole: adding an alias without a UUID drops the one
    it had before.
    """
    if device_id and not UUID_RE.match(device_id):
        raise ValueError(f"'{device_id}' is not a device UUID.")
    data = cfg.load(profile)
    table = _table(data)
    key = _stored_key(table, name) or name
    previous = table.get(key)
    table[key] = Alias(device, device_id)
    _save(data, table, profile)
    return previous


def remove(profile: str, name: str) -> bool:
    data = cfg.load(profile)
    table = _table(data)
    key = _stored_key(table, name)
    if key is None:
        return False
    del table[key]
    _save(data, table, profile)
    return True


def complete_device(ctx, incomplete: str) -> list[str]:
    """Suggest the active profile's aliases for a ``<device>`` argument.

    Purely local: shell completion must not depend on the network. The active
    profile comes from the root command's ``-c`` option, which sits several
    context levels up while completing a subcommand argument.
    """
    profile = "default"
    node = ctx
    while node is not None:
        chosen = (node.params or {}).get("config")
        if chosen:
            profile = chosen
            break
        node = node.parent
    return sorted(a for a in load(profile) if a.startswith(incomplete))
