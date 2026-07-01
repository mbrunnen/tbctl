# Rename `tb` to `tbctl`

## Scope

Rename the CLI tool from `tb` to `tbctl` throughout the project.

## Changes

| Location | Change |
|---|---|
| `tb/` directory | Rename to `tbctl/` |
| All `from tb.` imports | `from tbctl.` |
| `pyproject.toml` `name` | `"tb"` → `"tbctl"` |
| `pyproject.toml` `[project.scripts]` | `tb = "tb.cli:main"` → `tbctl = "tbctl.cli:main"` |
| `pyproject.toml` `packages` | `"tb"` → `"tbctl"` |
| `pyproject.toml` `known-first-party` | add `"tbctl"` (keep `"tb_client"`) |
| `tbctl/config.py` `CONFIG_DIR` | `".config/tb"` → `".config/tbctl"` |
| `CLAUDE.md` | All `tb` command references → `tbctl` |
| `README.md` | All `tb` command references → `tbctl` |

## Out of scope

The generated client `generated/tb_client/` is untouched.
