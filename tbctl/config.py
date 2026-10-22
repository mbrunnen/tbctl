import os
import sys
import tomllib
from pathlib import Path

import tomli_w

CONFIG_DIR = Path.home() / ".config" / "tbctl"
KEYS = ("url", "aliases")

_warned: set[tuple[Path, str]] = set()


def _path(profile: str) -> Path:
    return CONFIG_DIR / f"{profile}.toml"


def list_profiles() -> list[str]:
    if not CONFIG_DIR.exists():
        return []
    return sorted(p.stem for p in CONFIG_DIR.glob("*.toml"))


def load(profile: str = "default") -> dict:
    path = _path(profile)
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        data = tomllib.load(f)
    _warn_unknown(path, data)
    return data


def _warn_unknown(path: Path, data: dict) -> None:
    """Name each key tbctl does not use, once, but stay quiet for shell completion."""
    if "_TBCTL_COMPLETE" in os.environ:
        return
    for key in data:
        if key not in KEYS and (path, key) not in _warned:
            _warned.add((path, key))
            print(f"Warning: ignoring unknown key '{key}' in {path}", file=sys.stderr)


def save(data: dict, profile: str = "default") -> None:
    """Write a profile atomically, so a failed write cannot lose the old one."""
    path = _path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    try:
        with open(tmp, "wb") as f:
            tomli_w.dump(data, f)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
