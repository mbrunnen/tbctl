import os
import tomllib
from pathlib import Path

import tomli_w

CONFIG_DIR = Path.home() / ".config" / "tbctl"


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
        return tomllib.load(f)


def save(data: dict, profile: str = "default") -> None:
    """Write a profile atomically, so a failed write cannot lose the old one.

    The alias migration writes from a read path, which shell completion also
    reaches, so two processes may save at the same time.
    """
    path = _path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    try:
        with open(tmp, "wb") as f:
            tomli_w.dump(data, f)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
