"""Keys tbctl has seen per device, kept locally so shell completion needs no network.

The cache is kept per login, as ``<user>@<host>`` with the context's ``user``
from the config file: what a user may read decides the keys, so two contexts
with the same login share it. A context without ``user`` caches nothing.

The file maps each device UUID to its time-series keys and its attribute keys per
scope, and each device name tbctl resolved or listed to its UUID.
"""

import contextlib
import json
import os
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import quote, urlparse

import tbctl.aliases as aliases
import tbctl.config as cfg
from tbctl.config import Context

CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "tbctl"
TIMESERIES = "timeseries"


def _path(context: Context) -> Path | None:
    try:
        user = cfg.table(context).get("user")
    except Exception:
        return None
    if not user:
        return None
    return CACHE_DIR / quote(f"{user}@{urlparse(context.url).netloc}", safe="") / "keys.json"


def _load(context: Context) -> dict:
    path = _path(context)
    if path is None:
        return {}
    try:
        data = json.loads(path.read_text())
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


def _save(path: Path, data: dict) -> None:
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


def record(context: Context, device_id: str, kind: str, keys: Iterable[str], full: bool) -> None:
    """Store the keys of one kind for a device; a full listing replaces, a partial one adds."""
    path = _path(context)
    if path is None:
        return
    data = _load(context)
    entry = data.setdefault("devices", {}).setdefault(device_id, {})
    known = set() if full else set(entry.get(kind, []))
    entry[kind] = sorted(known | set(keys))
    _save(path, data)


def remember(context: Context, names: dict[str, str]) -> None:
    """Store the UUID of each device name, replacing what was known."""
    path = _path(context)
    if path is None or not names:
        return
    data = _load(context)
    data.setdefault("names", {}).update(names)
    _save(path, data)


def forget(context: Context, device_id: str) -> None:
    """Drop every cached name of a device."""
    path = _path(context)
    if path is None:
        return
    data = _load(context)
    names = data.get("names", {})
    stale = [name for name, uuid in names.items() if uuid == device_id]
    for name in stale:
        del names[name]
    if stale:
        _save(path, data)


def device_id(context: Context, name: str) -> str | None:
    return _load(context).get("names", {}).get(name)


def device_names(context: Context) -> list[str]:
    return sorted(_load(context).get("names", {}))


def lookup(context: Context, device: str, kind: str) -> list[str]:
    """Return the cached keys; a local alias resolves to its UUID or device name first."""
    data = _load(context)
    names = data.get("names", {})
    device = aliases.resolve(context, device) or device
    device_id = names.get(device, device)
    return list(data.get("devices", {}).get(device_id, {}).get(kind, []))


def _complete(ctx, incomplete: str, kind: str) -> list[str]:
    device = (ctx.params or {}).get("device")
    if not device:
        return []
    head, _, last = incomplete.rpartition(",")
    prefix = f"{head}," if head else ""
    taken = set(head.split(",")) if head else set()
    context = cfg.try_active(ctx)
    if context is None:
        return []
    keys = lookup(context, device, kind)
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
    context = cfg.try_active(ctx)
    if context is None:
        return []
    protected = protected_keys(context)
    return [
        k
        for k in lookup(context, device, scope)
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
