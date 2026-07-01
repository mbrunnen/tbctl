# Rename `tb` to `tbctl` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the CLI tool from `tb` to `tbctl` — the installed command, Python package directory, project name, config directory, and documentation.

**Architecture:** `git mv` renames the package directory; `sed` or direct edits replace all `from tb.` imports; `pyproject.toml` updates wire the new entry point. The generated `tb_client` package is untouched.

**Tech Stack:** Python/Typer, uv, ruff, pytest

## Global Constraints

- Python >= 3.11
- Do not touch `generated/tb_client/` or `generate.sh`
- Run `uv run pytest` to verify; run `pre-commit run --all-files` before committing

---

### Task 1: Rename package and update all imports

**Files:**
- Rename: `tb/` → `tbctl/`
- Modify: `tbctl/cli.py`
- Modify: `tbctl/config.py`
- Modify: `tbctl/commands/config_cmd.py`
- Modify: `tbctl/commands/attributes.py`
- Modify: `tbctl/commands/telemetry.py`
- Modify: `tbctl/commands/ota.py`
- Modify: `tbctl/commands/device.py`
- Modify: `tests/test_attributes.py`
- Modify: `tests/test_telemetry.py`
- Modify: `tests/test_client.py`
- Modify: `tests/test_device.py`
- Modify: `tests/test_ota.py`
- Modify: `tests/test_config.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `tbctl` Python package importable as `from tbctl.cli import app`

- [ ] **Step 1: Rename the package directory**

```bash
git mv tb tbctl
```

- [ ] **Step 2: Replace all intra-package imports**

```bash
find tbctl/ -name "*.py" -exec sed -i 's/from tb\./from tbctl./g; s/import tb\./import tbctl./g' {} +
```

- [ ] **Step 3: Update the config directory path**

In `tbctl/config.py` line 6, change:
```python
CONFIG_DIR = Path.home() / ".config" / "tb"
```
to:
```python
CONFIG_DIR = Path.home() / ".config" / "tbctl"
```

- [ ] **Step 4: Replace all test imports**

```bash
find tests/ -name "*.py" -exec sed -i 's/from tb\./from tbctl./g' {} +
```

- [ ] **Step 5: Update pyproject.toml**

Change `name`:
```toml
name = "tbctl"
```

Change `[project.scripts]`:
```toml
[project.scripts]
tbctl = "tbctl.cli:main"
```

Change `packages` under `[tool.hatch.build.targets.wheel]`:
```toml
packages = ["tbctl", "generated/tb_client"]
```

Change `known-first-party` under `[tool.ruff.lint.isort]`:
```toml
known-first-party = ["tb_client", "tbctl"]
```

- [ ] **Step 6: Reinstall the package so the new entry point is registered**

```bash
uv sync
```

- [ ] **Step 7: Run tests**

```bash
uv run pytest
```

Expected: all tests pass

- [ ] **Step 8: Run lint**

```bash
pre-commit run --all-files
```

Expected: all checks pass

- [ ] **Step 9: Commit**

```bash
git add tbctl/ tests/ pyproject.toml uv.lock
git commit -m "rename: tb -> tbctl (package, entry point, config dir)"
```

---

### Task 2: Update documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: renamed package from Task 1

- [ ] **Step 1: Update CLAUDE.md**

Replace every occurrence of `tb` as a command or path with `tbctl`:

```bash
sed -i \
  -e 's|uv run tb|uv run tbctl|g' \
  -e 's|uv run ruff check tb/|uv run ruff check tbctl/|g' \
  -e 's|uv run ruff format --check tb/|uv run ruff format --check tbctl/|g' \
  -e 's|--cov=tb |--cov=tbctl |g' \
  -e 's|tb --install-completion|tbctl --install-completion|g' \
  -e 's|`tb/cli.py`|`tbctl/cli.py`|g' \
  -e 's|`tb/config.py`|`tbctl/config.py`|g' \
  -e 's|`tb/commands/`|`tbctl/commands/`|g' \
  -e 's|~/.config/tb/|~/.config/tbctl/|g' \
  -e 's/`tb` is a CLI/`tbctl` is a CLI/' \
  -e 's|`tb config`|`tbctl config`|g' \
  -e 's|`tb ota`|`tbctl ota`|g' \
  CLAUDE.md
```

Review the result:
```bash
grep -n "tb" CLAUDE.md
```

Check that the only remaining `tb` occurrences are `tb_client` (the generated client package — intentionally unchanged).

- [ ] **Step 2: Update README.md**

```bash
sed -i \
  -e 's/^# tb$/# tbctl/' \
  -e 's/\btb \(config\|ota\|device\|telemetry\|attributes\|--install-completion\)/tbctl \1/g' \
  -e 's/pipx install tb$/pipx install tbctl/' \
  -e 's/pipx reinstall tb$/pipx reinstall tbctl/' \
  README.md
```

Review:
```bash
grep -n "\btb\b" README.md
```

Manually fix any remaining `tb` CLI references missed by the above.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: update tb -> tbctl references in CLAUDE.md and README.md"
```
