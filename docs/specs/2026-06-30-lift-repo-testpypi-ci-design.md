# Lift tbctl: TestPyPI publishing, CI fix, and .envrc

## Goal

Modernise the repository's release and developer-setup tooling:

1. Publish `tbctl` to **TestPyPI** from CI.
2. Fix the broken CI lint/format step (still references the pre-rename `tb/` path).
3. Add a `.envrc` (direnv) that sets up the uv environment and enables the
   pre-commit hooks.

## Decisions

- **Build backend**: keep `hatchling`. It already bundles both `tbctl` and the
  gitignored, generated `generated/tb_client` into the wheel. Switching to
  `uv_build` would require relocating the generated client (it lives outside any
  single module root) or renaming every `tb_client` import — churn for no
  benefit.
- **Publish trigger**: on `v*` git tag push only.
- **Publish auth**: Trusted Publishing (OIDC) — no stored secrets.
- **Target index**: TestPyPI only (no production PyPI).

## Components

### 1. Build backend — no change

`pyproject.toml` keeps `hatchling` and the existing
`[tool.hatch.build.targets.wheel] packages = ["tbctl", "generated/tb_client"]`.

### 2. CI fix — `.github/workflows/ci.yml`

The real breakage: the `lint-and-test` job lints and format-checks `tb/`, which
no longer exists after the `tb → tbctl` rename. Change both commands to target
`tbctl/ tests/`. No other change to `ci.yml`; its trigger and jobs stay as they
are.

### 3. TestPyPI publishing — dedicated `publish.yml`

A separate, self-contained workflow file `.github/workflows/publish.yml`,
triggered only by `v*` tag pushes. Keeping it separate from `ci.yml` avoids
cross-workflow artifact passing, so this workflow builds the distribution
itself.

- **Trigger**: `on: { push: { tags: ['v*'] } }`.
- **`publish-testpypi`** job:
  - `permissions: { id-token: write }`
  - checks out, sets up uv (Python 3.11) and Java 17, installs
    openapi-generator, runs `./generate.sh` (the generated client must be on
    disk to be bundled), then `uv build`.
  - calls `pypa/gh-action-pypi-publish` with
    `repository-url: https://test.pypi.org/legacy/` (OIDC Trusted Publishing,
    no `password`).

`ci.yml`'s `secret-scan` and `lint-and-test` jobs are unaffected.

### 4. `.envrc` (direnv)

```bash
# Set up the uv-managed venv and keep it in sync with uv.lock.
watch_file uv.lock pyproject.toml
uv sync
source .venv/bin/activate
# Enable git pre-commit hooks.
pre-commit install --install-hooks
```

`uv sync` installs the dev group, which provides `pre-commit` on PATH.
`pre-commit install --install-hooks` is idempotent and safe to run on every
direnv load.

## Manual setup required (one-time, by the maintainer)

- On TestPyPI, register a **pending publisher** for project `tbctl`: owner/repo,
  workflow filename `publish.yml`, environment (if used) matching the job.
- Install `direnv` locally and run `direnv allow` after the `.envrc` lands.
- Bump `version` in `pyproject.toml` before each tag — TestPyPI rejects
  re-uploads of an existing version.

## Out of scope

- `uv_build` migration.
- Dependency changes.
- Production PyPI publishing.
- Automated version bumping.
