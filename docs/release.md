# Release Process

AtlasBridge uses **Trusted Publishing (OIDC)** to publish to PyPI and TestPyPI.
No API tokens are stored in GitHub Secrets.

---

## Tag patterns

| Tag pattern | Example | Target |
|---|---|---|
| `vX.Y.ZrcN` | `v0.6.3rc1` | TestPyPI |
| `vX.Y.Z` | `v0.6.3` | PyPI (production) |

Release candidate tags (`rc`) **never** publish to production PyPI — an explicit
guard condition in the workflow prevents it.

---

## How to release

### 1. Release candidate (TestPyPI)

```bash
# Bump version in pyproject.toml and src/atlasbridge/__init__.py
# e.g. version = "0.6.3rc1"

git add -A && git commit -m "chore: bump version to v0.6.3rc1"
git tag v0.6.3rc1
git push origin main --tags
```

The `publish-testpypi.yml` workflow triggers automatically.
Verify the package at https://test.pypi.org/project/atlasbridge/.

Install and test:

```bash
pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ atlasbridge==0.6.3rc1
atlasbridge --version
```

### 2. Stable release (PyPI)

```bash
# Bump version to stable in pyproject.toml and src/atlasbridge/__init__.py
# e.g. version = "0.6.3"

git add -A && git commit -m "chore: bump version to v0.6.3"
git tag v0.6.3
git push origin main --tags
```

The `publish-pypi.yml` workflow triggers automatically.
Verify the package at https://pypi.org/project/atlasbridge/.

---

## GitHub Environments setup

Two GitHub Environments must exist with **no required reviewers** (fully automatic):

### `testpypi`

1. Go to **Settings → Environments** in the GitHub repo.
2. Create environment named `testpypi`.
3. Leave "Required reviewers" empty (no approval gates).
4. No secrets needed — publishing uses OIDC.

### `pypi`

1. Go to **Settings → Environments** in the GitHub repo.
2. Create environment named `pypi`.
3. Leave "Required reviewers" empty (no approval gates).
4. No secrets needed — publishing uses OIDC.

---

## Trusted Publisher configuration

### TestPyPI

1. Go to https://test.pypi.org/manage/account/publishing/.
2. Under "Add a new pending publisher" (or manage existing project):
   - **PyPI project name**: `atlasbridge`
   - **Owner**: `abdulraoufatia`
   - **Repository**: `atlasbridge`
   - **Workflow name**: `publish-testpypi.yml`
   - **Environment name**: `testpypi`
3. Click "Add".

### PyPI

1. Go to https://pypi.org/manage/account/publishing/.
2. Under "Add a new pending publisher" (or manage existing project):
   - **PyPI project name**: `atlasbridge`
   - **Owner**: `abdulraoufatia`
   - **Repository**: `atlasbridge`
   - **Workflow name**: `publish-pypi.yml`
   - **Environment name**: `pypi`
3. Click "Add".

---

## UI asset verification

Both publish workflows and CI include an automated check that verifies `.tcss`
files are present in the built wheel. This prevents the `StylesheetError` crash
that occurred when UI assets were missing from the distribution.

The check:
1. Builds the wheel.
2. Inspects the `.whl` zip for files ending in `.tcss`.
3. Fails the workflow if no `.tcss` files are found.

CI also runs a **packaging smoke test** that:
1. Builds the wheel.
2. Installs it into a clean venv (not editable mode).
3. Loads `.tcss` files via `importlib.resources` (same path the app uses at runtime).
4. Verifies the CLI entry point works (`atlasbridge --version`).

---

## Checklist before tagging

1. Version bumped in both `pyproject.toml` and `src/atlasbridge/__init__.py`.
2. Changelog updated in `README.md`.
3. All CI checks pass on `main`.
4. `ruff format .` has been run.
5. Tag pushed to `origin` (tags are not pushed by default with `git push`).
