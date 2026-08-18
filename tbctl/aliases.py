"""Local device aliases, stored per config profile.

An alias maps a free-text name to a ThingsBoard device name, so
``tbctl telemetry latest ruedi`` works in place of the device's own name.
Aliases live in the profile's own config file and never touch the server.
"""

import tbctl.config as cfg


def load(profile: str = "default") -> dict[str, str]:
    return cfg.load(profile).get("aliases", {})


def _stored_key(table: dict[str, str], name: str) -> str | None:
    """Return the stored key matching ``name`` case-insensitively."""
    folded = name.casefold()
    for key in table:
        if key.casefold() == folded:
            return key
    return None


def resolve(profile: str, name: str) -> str | None:
    table = load(profile)
    key = _stored_key(table, name)
    return table[key] if key else None


def add(profile: str, name: str, device: str) -> str | None:
    """Point ``name`` at ``device``, returning the target it replaced."""
    data = cfg.load(profile)
    table = data.get("aliases", {})
    key = _stored_key(table, name) or name
    previous = table.get(key)
    table[key] = device
    data["aliases"] = table
    cfg.save(data, profile)
    return previous


def remove(profile: str, name: str) -> bool:
    data = cfg.load(profile)
    table = data.get("aliases", {})
    key = _stored_key(table, name)
    if key is None:
        return False
    del table[key]
    data["aliases"] = table
    cfg.save(data, profile)
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
