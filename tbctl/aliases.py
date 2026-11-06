"""Local device aliases, stored per context.

An alias maps a free-text name to a device: the device's ThingsBoard name and,
optionally, its UUID. ``tbctl telemetry latest ruedi`` then works in place of
the device's own name, and a stored UUID lets that resolve without the
name lookup, which needs tenant device-read permission. Aliases live in the
context's table of the config file and never touch the server.
"""

import re
from typing import NamedTuple

import tomlkit

import tbctl.config as cfg
from tbctl.config import Context

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


class Alias(NamedTuple):
    """The device an alias points at: its name, plus its UUID when known."""

    name: str
    id: str | None = None


def _entry(value: dict) -> Alias:
    return Alias(value["name"], value.get("id"))


def _stored(alias: Alias):
    """Render an alias for TOML, which has no way to store a missing UUID."""
    stored = tomlkit.inline_table()
    stored["name"] = alias.name
    if alias.id:
        stored["id"] = alias.id
    return stored


def _table(data: dict) -> dict[str, Alias]:
    return {name: _entry(value) for name, value in data.get("aliases", {}).items()}


def load(context: Context) -> dict[str, Alias]:
    return _table(cfg.table(context))


def _stored_key(table: dict[str, Alias], name: str) -> str | None:
    """Return the stored key matching ``name`` case-insensitively."""
    folded = name.casefold()
    for key in table:
        if key.casefold() == folded:
            return key
    return None


def resolve(context: Context, name: str) -> Alias | None:
    table = load(context)
    key = _stored_key(table, name)
    return table[key] if key else None


def _context_table(doc, context: Context):
    try:
        return doc["contexts"][context.name]
    except KeyError:
        raise cfg.ConfigError(f"context '{context.name}' not in {context.file}") from None


def add(context: Context, name: str, device: str, device_id: str | None = None) -> Alias | None:
    """Point ``name`` at a device, returning the entry it replaced.

    The entry is replaced whole: adding an alias without a UUID drops the one
    it had before. Only this entry is written, so comments in the file stay.
    """
    if device_id and not UUID_RE.match(device_id):
        raise ValueError(f"'{device_id}' is not a device UUID.")
    doc = cfg.read(context.file)
    entry = _context_table(doc, context)
    table = _table(entry)
    key = _stored_key(table, name) or name
    previous = table.get(key)
    if "aliases" not in entry:
        entry["aliases"] = tomlkit.table()
    entry["aliases"][key] = _stored(Alias(device, device_id))
    cfg.write(context.file, doc)
    return previous


def remove(context: Context, name: str) -> bool:
    doc = cfg.read(context.file)
    entry = _context_table(doc, context)
    key = _stored_key(_table(entry), name)
    if key is None:
        return False
    del entry["aliases"][key]
    if not entry["aliases"]:
        del entry["aliases"]
    cfg.write(context.file, doc)
    return True


def complete_device(ctx, incomplete: str) -> list[str]:
    """Suggest the active context's aliases and cached device names for ``<device>``.

    Purely local: shell completion must not depend on the network.
    """
    from tbctl import keycache

    context = cfg.try_active(ctx)
    if context is None:
        return []
    names = set(load(context)) | set(keycache.device_names(context))
    return sorted(n for n in names if n.startswith(incomplete))
