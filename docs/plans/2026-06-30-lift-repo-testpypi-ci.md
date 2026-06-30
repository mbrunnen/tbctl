# Lift tbctl: TestPyPI, CI fix, .envrc — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the broken CI, publish `tbctl` to TestPyPI on version-tag pushes via Trusted Publishing, and add a `.envrc` that sets up uv and enables pre-commit hooks.

**Architecture:** A single GitHub Actions workflow (`ci.yml`) keeps its `secret-scan` and `lint-and-test` jobs; `lint-and-test` gains a build-and-upload-artifact step, and a new `publish-testpypi` job (gated on `v*` tags, OIDC) consumes that artifact. A `.envrc` drives local setup via direnv. The hatchling build backend is unchanged.

**Tech Stack:** GitHub Actions, `astral-sh/setup-uv`, `pypa/gh-action-pypi-publish`, hatchling, uv, direnv, pre-commit.

## Global Constraints

- Build backend stays `hatchling`; do **not** migrate to `uv_build`.
- The wheel must bundle both `tbctl` and `generated/tb_client`; the generated client must exist on disk (via `./generate.sh`) before any build.
- Publish target is **TestPyPI only**: `repository-url: https://test.pypi.org/legacy/`.
- Publish runs **only on `v*` tag pushes** and uses **Trusted Publishing (OIDC)** — no `password`, no stored secrets.
- Lint/format target is `tbctl/ tests/` (never the removed `tb/` path).
- Files end with a trailing newline `\n`.
- No useless inline comments.

---

### Task 1: Fix the broken CI lint/format paths and extend the trigger

The `lint-and-test` job lints and format-checks `tb/`, which was removed in the `tb → tbctl` rename, so every CI run fails. Fix the paths and extend the trigger to fire on version tags (needed by Task 2's publish job).

**Files:**
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: nothing.
- Produces: a passing `lint-and-test` job and a workflow that triggers on `push` to `main`, on `v*` tags, and on `pull_request`.

- [ ] **Step 1: Update the trigger and lint/format paths**

Replace the `on:` block and the two `ruff` steps in `.github/workflows/ci.yml`.

Change the trigger from:

```yaml
on:
  push:
    branches: [main]
  pull_request:
```

to:

```yaml
on:
  push:
    branches: [main]
    tags: ['v*']
  pull_request:
```

Change the two ruff steps from:

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

### Task 2: Build artifacts in lint-and-test and add the TestPyPI publish job

After tests pass, build the distribution and upload it as an artifact; add a gated `publish-testpypi` job that downloads the artifact and publishes to TestPyPI via OIDC. Building and publishing are coupled (the publish job consumes the build's artifact), so they land together.

**Files:**
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: the `lint-and-test` job and tag trigger from Task 1.
- Produces: a `dist` artifact (sdist + wheel) from `lint-and-test`, and a `publish-testpypi` job that runs only on `v*` tags.

- [ ] **Step 1: Add build + upload steps to the end of `lint-and-test`**

After the existing `- run: uv run pytest` step, append:

```yaml
      - name: Build distribution
        run: uv build
      - name: Upload distribution
        uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/
```

- [ ] **Step 2: Add the publish-testpypi job**

Append a new job at the end of the file (sibling of `lint-and-test`):

```yaml
  publish-testpypi:
    needs: lint-and-test
    if: startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-latest
    permissions:
      id-token: write
    steps:
      - name: Download distribution
        uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/
      - name: Publish to TestPyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          repository-url: https://test.pypi.org/legacy/
```

- [ ] **Step 3: Verify the workflow is valid YAML and the job parses**

Run:
```bash
python3 -c "import yaml,sys; d=yaml.safe_load(open('.github/workflows/ci.yml')); assert 'publish-testpypi' in d['jobs']; assert d['jobs']['publish-testpypi']['needs']=='lint-and-test'; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Verify no stored-secret password is used (OIDC only)**

Run: `grep -n 'password' .github/workflows/ci.yml || echo "no password field"`
Expected: `no password field`

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: publish to TestPyPI on version tags via trusted publishing"
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
- TestPyPI publish on tag, OIDC → Task 2. ✓
- CI fix (`tb/` → `tbctl/`) → Task 1. ✓
- `.envrc` sets up uv + enables pre-commit → Task 3. ✓
- Build backend unchanged (hatchling) → Global Constraints; no task touches `pyproject.toml` build config. ✓

**Placeholder scan:** No TBD/TODO; every code/config block is complete. ✓

**Type consistency:** Artifact name `dist` is produced (upload, Task 2 Step 1) and consumed (download, Task 2 Step 2) identically; job name `publish-testpypi` and dependency `lint-and-test` match across steps. ✓

## Notes for the maintainer (manual, outside this plan)

- On TestPyPI, register a **pending publisher** for project `tbctl` (owner/repo, workflow filename `ci.yml`) before the first tag push.
- Install `direnv` and run `direnv allow` after Task 3.
- Bump `version` in `pyproject.toml` before each `v*` tag — TestPyPI rejects re-uploads of an existing version.
