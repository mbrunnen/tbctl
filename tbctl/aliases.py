"""Local device aliases, stored per context.

An alias maps a free-text name to a device name: ``tbctl telemetry latest
ruedi`` then works in place of the device's own name. Aliases live in the
context's table of the config file and never touch the server.
"""

import re

import tomlkit

import tbctl.config as cfg
from tbctl.config import Context

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


def _table(data: dict) -> dict[str, str]:
    return {alias: value["name"] for alias, value in data.get("aliases", {}).items()}


def load(context: Context) -> dict[str, str]:
    return _table(cfg.table(context))


def _stored_key(table: dict[str, str], name: str) -> str | None:
    """Return the stored key matching ``name`` case-insensitively."""
    folded = name.casefold()
    for key in table:
        if key.casefold() == folded:
            return key
    return None


def resolve(context: Context, name: str) -> str | None:
    table = load(context)
    key = _stored_key(table, name)
    return table[key] if key else None


def _context_table(doc, context: Context):
    try:
        return doc["contexts"][context.name]
    except KeyError:
        raise cfg.ConfigError(f"context '{context.name}' not in {context.file}") from None


def add(context: Context, name: str, device: str) -> str | None:
    """Point ``name`` at a device, returning the device name it replaced.

    Only this entry is written, so comments in the file stay.
    """
    doc = cfg.read(context.file)
    entry = _context_table(doc, context)
    table = _table(entry)
    key = _stored_key(table, name) or name
    previous = table.get(key)
    if "aliases" not in entry:
        entry["aliases"] = tomlkit.table()
    stored = tomlkit.inline_table()
    stored["name"] = device
    entry["aliases"][key] = stored
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


def complete_alias(ctx, incomplete: str) -> list[str]:
    """Suggest the active context's aliases, without cached device names."""
    context = cfg.try_active(ctx)
    if context is None:
        return []
    return sorted(a for a in load(context) if a.startswith(incomplete))
