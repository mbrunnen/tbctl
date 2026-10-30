"""Keys tbctl has seen per device, kept locally so shell completion needs no network.

The file maps each device UUID to its time-series keys and its attribute keys per
scope, and each name or alias the user typed to the UUID it resolved to.
"""

import contextlib
import json
import os
from collections.abc import Iterable
from pathlib import Path

import tbctl.aliases as aliases

CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "tbctl"
TIMESERIES = "timeseries"


def _path(profile: str) -> Path:
    return CACHE_DIR / profile / "keys.json"


def _load(profile: str) -> dict:
    try:
        data = json.loads(_path(profile).read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    names, devices = data.get("names", {}), data.get("devices", {})
    if not isinstance(names, dict) or not isinstance(devices, dict):
        return {}
    if not all(isinstance(entry, dict) for entry in devices.values()):
        return {}
    return data


def record(
    profile: str, device: str, device_id: str, kind: str, keys: Iterable[str], full: bool
) -> None:
    """Store the keys of one kind for a device; a full listing replaces, a partial one adds."""
    data = _load(profile)
    names = data.setdefault("names", {})
    if device != device_id:
        names[device] = device_id
    entry = data.setdefault("devices", {}).setdefault(device_id, {})
    known = set() if full else set(entry.get(kind, []))
    entry[kind] = sorted(known | set(keys))

    path = _path(profile)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    with contextlib.suppress(OSError):
        try:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(path.parent, 0o700)
            with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
                json.dump(data, f)
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)


def lookup(profile: str, device: str, kind: str) -> list[str]:
    """Return the cached keys; a local alias resolves to its UUID or device name first."""
    data = _load(profile)
    names = data.get("names", {})
    alias = aliases.resolve(profile, device)
    if alias:
        device = alias.id or alias.name
    device_id = names.get(device, device)
    return list(data.get("devices", {}).get(device_id, {}).get(kind, []))


def _complete(ctx, incomplete: str, kind: str) -> list[str]:
    device = (ctx.params or {}).get("device")
    if not device:
        return []
    head, _, last = incomplete.rpartition(",")
    prefix = f"{head}," if head else ""
    taken = set(head.split(",")) if head else set()
    keys = lookup(aliases.active_profile(ctx), device, kind)
    return [prefix + k for k in keys if k.startswith(last) and k not in taken]


def complete_timeseries_keys(ctx, incomplete: str) -> list[str]:
    return _complete(ctx, incomplete, TIMESERIES)


def complete_attribute_keys(ctx, incomplete: str) -> list[str]:
    from tbctl.commands.attributes import normalise_scope

    scope = normalise_scope((ctx.params or {}).get("scope") or "shared")
    return _complete(ctx, incomplete, scope) if scope else []


def _writable(ctx, incomplete: str, given: set[str]) -> list[str]:
    from tbctl.commands.attributes import normalise_scope, protected_keys

    params = ctx.params or {}
    device = params.get("device")
    scope = normalise_scope(params.get("scope") or "shared")
    if not device or scope in (None, "CLIENT_SCOPE"):
        return []
    profile = aliases.active_profile(ctx)
    protected = protected_keys(profile)
    return [
        k
        for k in lookup(profile, device, scope)
        if k.startswith(incomplete) and k not in protected and k not in given
    ]


def complete_writable_keys(ctx, incomplete: str) -> list[str]:
    return _writable(ctx, incomplete, set((ctx.params or {}).get("keys") or ()))


def complete_writable_pairs(ctx, incomplete: str) -> list[str]:
    given = {
        p[0] if isinstance(p, tuple) else p.partition("=")[0]
        for p in (ctx.params or {}).get("pairs") or ()
    }
    return [f"{k}=" for k in _writable(ctx, incomplete, given)]
