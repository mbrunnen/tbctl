# Lift tbctl: TestPyPI, CI fix, .envrc — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the broken CI, publish `tbctl` to TestPyPI on version-tag pushes via Trusted Publishing, and add a `.envrc` that sets up uv and enables pre-commit hooks.

**Architecture:** `ci.yml` keeps its `secret-scan` and `lint-and-test` jobs and only gets its broken lint/format paths fixed. A dedicated, self-contained `publish.yml` (triggered by `v*` tags) builds the distribution and publishes to TestPyPI via OIDC. A `.envrc` drives local setup via direnv. The hatchling build backend is unchanged.

**Tech Stack:** GitHub Actions, `astral-sh/setup-uv`, `pypa/gh-action-pypi-publish`, hatchling, uv, direnv, pre-commit.

## Global Constraints

- Build backend stays `hatchling`; do **not** migrate to `uv_build`.
- The wheel must bundle both `tbctl` and `generated/tb_client`; the generated client must exist on disk (via `./generate.sh`) before any build.
- Publish target is **TestPyPI only**: `repository-url: https://test.pypi.org/legacy/`.
- Publishing lives in a dedicated `.github/workflows/publish.yml`, triggered **only on `v*` tag pushes**, using **Trusted Publishing (OIDC)** — no `password`, no stored secrets.
- Lint/format target is `tbctl/ tests/` (never the removed `tb/` path).
- Files end with a trailing newline `\n`.
- No useless inline comments.

---

### Task 1: Fix the broken CI lint/format paths

The `lint-and-test` job lints and format-checks `tb/`, which was removed in the `tb → tbctl` rename, so every CI run fails. Fix the paths only; the trigger and jobs are otherwise unchanged.

**Files:**
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: nothing.
- Produces: a passing `lint-and-test` job.

- [ ] **Step 1: Update the two ruff steps**

In `.github/workflows/ci.yml`, change:

```yaml
      - run: uv run ruff check tb/ tests/
      - run: uv run ruff format --check tb/ tests/
```

to:

```yaml
      - run: uv run ruff check tbctl/ tests/
      - run: uv run ruff format --check tbctl/ tests/
```

- [ ] **Step 2: Verify the workflow is valid YAML**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))" && echo OK`
Expected: `OK`

- [ ] **Step 3: Verify the stale path is gone**

Run: `grep -n 'tb/' .github/workflows/ci.yml || echo "no stale tb/ path"`
Expected: `no stale tb/ path`

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: fix lint/format paths after tb to tbctl rename"
```

---

### Task 2: Add the dedicated TestPyPI publish workflow

Create a self-contained `publish.yml` that fires on `v*` tags, builds the distribution (generating the client first), and publishes to TestPyPI via OIDC. It builds its own artifact rather than reaching into `ci.yml`, so the two workflows stay independent.

**Files:**
- Create: `.github/workflows/publish.yml`

**Interfaces:**
- Consumes: `./generate.sh`, `pyproject.toml` (hatchling build).
- Produces: a TestPyPI upload of `tbctl` on each `v*` tag.

- [ ] **Step 1: Create `.github/workflows/publish.yml`**

```yaml
name: Publish

on:
  push:
    tags: ['v*']

jobs:
  publish-testpypi:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.11"
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"
      - name: Generate tb_client
        run: |
          npm install -g @openapitools/openapi-generator-cli
          ./generate.sh
      - name: Build distribution
        run: uv build
      - name: Publish to TestPyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          repository-url: https://test.pypi.org/legacy/
```

- [ ] **Step 2: Verify the workflow is valid YAML and gated on tags + OIDC**

Run:
```bash
python3 -c "import yaml; d=yaml.safe_load(open('.github/workflows/publish.yml')); assert d['on']['push']['tags']==['v*']; assert d['jobs']['publish-testpypi']['permissions']['id-token']=='write'; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Verify no stored-secret password is used (OIDC only)**

Run: `grep -n 'password' .github/workflows/publish.yml || echo "no password field"`
Expected: `no password field`

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/publish.yml
git commit -m "ci: add publish.yml to release to TestPyPI on version tags"
```

---

### Task 3: Add the `.envrc` for direnv

Provide a one-step local setup: sync the uv venv, activate it, and install the pre-commit git hooks.

**Files:**
- Create: `.envrc`

**Interfaces:**
- Consumes: `pyproject.toml` and `uv.lock` (the dev group provides `pre-commit`).
- Produces: an activated `.venv` and installed git hooks after `direnv allow`.

- [ ] **Step 1: Create `.envrc`**

```bash
# Set up the uv-managed venv and keep it in sync with uv.lock.
watch_file uv.lock pyproject.toml
uv sync
source .venv/bin/activate
# Enable git pre-commit hooks.
pre-commit install --install-hooks
```

- [ ] **Step 2: Allow and load it, verifying the venv and hooks**

Run:
```bash
direnv allow . && direnv exec . sh -c 'command -v tbctl && test -f .git/hooks/pre-commit && echo OK'
```
Expected: a path under `.venv/bin/tbctl` followed by `OK`

- [ ] **Step 3: Commit**

```bash
git add .envrc
git commit -m "chore: add .envrc to set up uv and pre-commit hooks"
```

---

## Self-Review

**Spec coverage:**
- TestPyPI publish on tag, OIDC, dedicated `publish.yml` → Task 2. ✓
- CI fix (`tb/` → `tbctl/`) → Task 1. ✓
- `.envrc` sets up uv + enables pre-commit → Task 3. ✓
- Build backend unchanged (hatchling) → Global Constraints; no task touches `pyproject.toml` build config. ✓

**Placeholder scan:** No TBD/TODO; every code/config block is complete. ✓

**Type consistency:** `publish.yml` is self-contained (no artifact handoff); its tag trigger `['v*']` and `id-token: write` permission match the verification step. `ci.yml` and `publish.yml` are independent workflows with no shared names to drift. ✓

## Notes for the maintainer (manual, outside this plan)

- On TestPyPI, register a **pending publisher** for project `tbctl` (owner/repo, workflow filename `publish.yml`) before the first tag push.
- Install `direnv` and run `direnv allow` after Task 3.
- Bump `version` in `pyproject.toml` before each `v*` tag — TestPyPI rejects re-uploads of an existing version.
