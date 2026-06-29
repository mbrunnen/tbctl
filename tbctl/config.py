import tomllib
from pathlib import Path

import tomli_w

CONFIG_DIR = Path.home() / ".config" / "tbctl"


def _path(profile: str) -> Path:
    return CONFIG_DIR / f"{profile}.toml"


def load(profile: str = "default") -> dict:
    path = _path(profile)
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def save(data: dict, profile: str = "default") -> None:
    path = _path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        tomli_w.dump(data, f)
