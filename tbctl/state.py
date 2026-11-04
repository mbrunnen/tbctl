"""What tbctl writes itself: the login state of each context.

The config file belongs to the user and may sit in a repository, so the kind
of credential, the refresh expiry, the customer and, without a Secret Service,
the secret itself live here instead, one table per context key.
"""

import fcntl
import os
import threading
import tomllib
from pathlib import Path

import tomli_w

import tbctl.config as cfg

STATE_DIR = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "tbctl"


def _path() -> Path:
    return STATE_DIR / "state.toml"


def _ensure_dir() -> None:
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(STATE_DIR, 0o700)


def _all() -> dict:
    path = _path()
    if not path.exists():
        return {}
    cfg.check_private(path)
    with open(path, "rb") as f:
        return tomllib.load(f)


def load(key: str) -> dict:
    return dict(_all().get(key, {}))


def save(key: str, data: dict) -> None:
    """Replace the table of one context; an empty one removes it.

    Every context shares the file, so the read-modify-write runs under a lock:
    otherwise a login in one context could revert a renewal in another.
    """
    _ensure_dir()
    with open(STATE_DIR / "state.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        everything = _all()
        if data:
            everything[key] = data
        else:
            everything.pop(key, None)
        path = _path()
        tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as f:
                tomli_w.dump(everything, f)
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)


def lock_path(safe_key: str) -> Path:
    _ensure_dir()
    return STATE_DIR / f"{safe_key}.lock"
