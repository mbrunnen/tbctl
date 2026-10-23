import os
import sys
import tomllib
from pathlib import Path

import tomli_w

CONFIG_DIR = Path.home() / ".config" / "tbctl"
KEYS = ("url", "aliases", "token", "token_id", "token_expires")

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
    problems = [(key, f"unknown key '{key}'") for key in data if key not in KEYS]
    if "token_id" not in data:
        problems += [
            (key, f"'{key}' without 'token_id'; run `tbctl auth login`")
            for key in ("token", "token_expires")
            if key in data
        ]
    elif "token_expires" not in data:
        problems.append(("token_id", "'token_id' without 'token_expires'; run `tbctl auth login`"))
    for key, problem in problems:
        if (path, key) not in _warned:
            _warned.add((path, key))
            print(f"Warning: ignoring {problem} in {path}", file=sys.stderr)


def save(data: dict, profile: str = "default") -> None:
    """Write a profile atomically and readable only by the user.

    The file may hold the API key when no Secret Service is available.
    """
    path = _path(profile)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    try:
        with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as f:
            tomli_w.dump(data, f)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
