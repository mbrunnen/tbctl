import os
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import tomlkit
import typer

CONFIG_DIR = Path.home() / ".config" / "tbctl"
CONFIG_ENV = "TBCTL_CONFIG"
CONTEXT_ENV = "TBCTL_CONTEXT"
CONTEXT_KEYS = ("url", "user", "default", "aliases", "protected_attributes")
TOP_KEYS = ("contexts", "protected_attributes")


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Context:
    file: Path
    file_source: str
    name: str
    name_source: str
    url: str

    @property
    def key(self) -> str:
        return f"{self.name}@{self.url}"

    @property
    def safe_key(self) -> str:
        return quote(self.key, safe="")


def default_file() -> Path:
    return CONFIG_DIR / "config.toml"


def config_file(flag: str | None) -> tuple[Path, str]:
    if flag:
        if os.sep not in flag and not flag.endswith(".toml") and not Path(flag).exists():
            raise ConfigError(f"config file '{flag}' not found; did you mean --context {flag}?")
        return Path(flag), "flag"
    if os.environ.get(CONFIG_ENV):
        return Path(os.environ[CONFIG_ENV]), "env"
    return default_file(), "default"


def normalise_url(url: str) -> str:
    return url.rstrip("/")


def read(path: Path) -> tomlkit.TOMLDocument:
    """Return the config document, empty when the file is missing."""
    if not path.exists():
        return tomlkit.document()
    doc = tomlkit.parse(path.read_text())
    _warn_unknown_keys(path, doc)
    return doc


def _warn_unknown_keys(path: Path, doc) -> None:
    problems = [key for key in doc if key not in TOP_KEYS]
    for table in contexts(doc).values():
        problems += [key for key in table if key not in CONTEXT_KEYS]
    _warn(path, [(key, f"unknown key '{key}'") for key in problems])


def write(path: Path, doc: tomlkit.TOMLDocument) -> None:
    """Write atomically through a symlink, keeping the file's mode."""
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(tomlkit.dumps(doc))
        if path.exists():
            os.chmod(tmp, path.stat().st_mode & 0o777)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def contexts(doc) -> dict[str, dict]:
    table = doc.get("contexts", {})
    return table.unwrap() if hasattr(table, "unwrap") else dict(table)


def _select(path: Path, found: dict, context_flag: str | None) -> tuple[str, str]:
    if context_flag:
        return context_flag, "flag"
    if os.environ.get(CONTEXT_ENV):
        return os.environ[CONTEXT_ENV], "env"
    defaults = [name for name, table in found.items() if table.get("default") is True]
    if len(defaults) > 1:
        raise ConfigError(f"more than one context has default = true in {path}")
    if defaults:
        return defaults[0], "default"
    if len(found) == 1:
        return next(iter(found)), "only"
    if not found:
        raise ConfigError(f"no context in {path}; run `tbctl auth login`")
    raise ConfigError(f"several contexts in {path}; pass --context NAME or set default = true")


def resolve(config_flag: str | None = None, context_flag: str | None = None) -> Context:
    path, file_source = config_file(config_flag)
    found = contexts(read(path))
    name, name_source = _select(path, found, context_flag)
    if name not in found:
        raise ConfigError(f"context '{name}' not in {path}")
    url = found[name].get("url")
    if not url:
        raise ConfigError(f"context '{name}' has no url in {path}")
    return Context(path, file_source, name, name_source, normalise_url(url))


def add_context(path: Path, name: str, url: str, user: str | None = None) -> None:
    """Add a context; the first one in a file becomes the default."""
    doc = read(path)
    if "contexts" not in doc:
        doc["contexts"] = tomlkit.table(is_super_table=True)
    entry = tomlkit.table()
    entry["url"] = normalise_url(url)
    if user:
        entry["user"] = user
    if not contexts(doc):
        entry["default"] = True
    doc["contexts"][name] = entry
    write(path, doc)


def table(context: Context) -> dict:
    return contexts(read(context.file)).get(context.name, {})


_warned: set[tuple[Path, str]] = set()


def check_private(path: Path) -> None:
    """Refuse a file others can read: it may hold a credential."""
    for target, mode in ((path.parent, 0o700), (path, 0o600)):
        actual = target.stat().st_mode & 0o777
        if actual & 0o077:
            if "_TBCTL_COMPLETE" in os.environ:
                raise typer.Exit(1)
            typer.echo(
                f"Permissions {actual:o} for {target} are too open. Run `chmod {mode:o} {target}`.",
                err=True,
            )
            raise typer.Exit(1)


def _warn(path: Path, problems: list[tuple[str, str]]) -> None:
    if "_TBCTL_COMPLETE" in os.environ:
        return
    for key, problem in problems:
        if (path, key) not in _warned:
            _warned.add((path, key))
            print(f"Warning: ignoring {problem} in {path}", file=sys.stderr)


def choice(ctx) -> tuple[str | None, str | None]:
    """Find the root options ``-c`` and ``--context``, which sit several levels up."""
    config = context = None
    node = ctx
    while node is not None:
        params = node.params or {}
        config = config or params.get("config")
        context = context or params.get("context")
        node = node.parent
    return config, context


def active(ctx) -> Context:
    """Resolve the context of this command once, or stop with the reason."""
    root = ctx.find_root()
    root.ensure_object(dict)
    if "context" not in root.obj:
        try:
            root.obj["context"] = resolve(*choice(ctx))
        except ConfigError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)
    return root.obj["context"]


def try_active(ctx) -> Context | None:
    """Resolve quietly for shell completion, which must never fail or print."""
    try:
        return resolve(*choice(ctx))
    except Exception:
        return None
