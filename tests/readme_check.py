"""Verify that every ``tbctl`` command in the README still exists in the CLI.

Typer compiles to a Click command tree, so the documented command paths and
options can be checked against the real command objects without running them.
Typer vendors its own Click, so command/option kinds are detected structurally
(groups own a ``commands`` mapping; options expose dash-prefixed ``opts``)
rather than by ``isinstance`` against the public ``click`` package.
"""

import re
import shlex

import typer

_COMMAND_RE = re.compile(r"^\s*(?:\$\s+)?(?:uv run\s+)?(tbctl\b.*)$")
_TRAILING_COMMENT_RE = re.compile(r"\s+#.*$")


def root_command(typer_app: typer.Typer):
    """Return the Click command backing a Typer app."""
    return typer.main.get_command(typer_app)


def iter_command_lines(text: str) -> list[str]:
    """Extract ``tbctl`` invocations from fenced code blocks in markdown."""
    lines: list[str] = []
    in_fence = False
    for raw in text.splitlines():
        if raw.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            continue
        match = _COMMAND_RE.match(raw)
        if not match:
            continue
        command = _TRAILING_COMMENT_RE.sub("", match.group(1)).strip()
        if command:
            lines.append(command)
    return lines


def _is_group(command) -> bool:
    return hasattr(command, "commands")


def _options(command):
    """Yield ``(flag, takes_value)`` for every option flag on a command."""
    for param in command.params:
        flags = [opt for opt in (*param.opts, *param.secondary_opts) if opt.startswith("-")]
        if not flags:
            continue
        takes_value = not getattr(param, "is_flag", False) and not getattr(param, "count", False)
        for flag in flags:
            yield flag, takes_value


def check_invocation(root, line: str) -> list[str]:
    """Return drift errors for one README command line (empty means valid)."""
    try:
        tokens = shlex.split(line)
    except ValueError:
        return [f"{line!r}: could not parse"]
    if not tokens or tokens[0] != "tbctl":
        return []

    global_value_flags = {flag for flag, takes_value in _options(root) if takes_value}
    errors: list[str] = []
    node = root
    path = ["tbctl"]
    used_flags: list[str] = []
    resolving = True
    skip_value = False

    for token in tokens[1:]:
        if skip_value:
            skip_value = False
            continue
        if token.startswith("-"):
            name = token.split("=", 1)[0]
            used_flags.append(name)
            if resolving and "=" not in token and name in global_value_flags:
                skip_value = True
            continue
        if resolving and _is_group(node):
            if token in node.commands:
                node = node.commands[token]
                path.append(token)
                continue
            errors.append(f"{line!r}: unknown command '{token}' under '{' '.join(path)}'")
        resolving = False

    valid_flags = {flag for flag, _ in _options(node)} | {flag for flag, _ in _options(root)}
    valid_flags.add("--help")
    for name in used_flags:
        if name not in valid_flags:
            errors.append(f"{line!r}: unknown option '{name}' for '{' '.join(path)}'")
    return errors
