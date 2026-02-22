# Releasing AtlasBridge

This document describes how releases are cut and published.

---

## Release Process

1. **All CI checks must be green on `main`** before tagging.
2. **Bump version** in both `pyproject.toml` and `src/atlasbridge/__init__.py`.
3. **Update `CHANGELOG.md`** — move items from `[Unreleased]` to a new version section.
4. **Commit and push** the version bump to `main`.
5. **Tag the release**: `git tag v<X.Y.Z> && git push origin v<X.Y.Z>`.
6. **GitHub Actions publishes** the package to PyPI automatically on tag push.

---

## Rules

- **Releases are tag-only.** Push to `main` never publishes to PyPI.
- **If CI is red, do not tag.** Fix CI first.
- **Tag format:** `vX.Y.Z` (e.g., `v0.9.5`, `v1.0.0`).
- **RC tags:** `vX.Y.Z-rcN` (e.g., `v1.0.0-rc1`) publish to TestPyPI, not PyPI.
- **No auto-merge.** All PRs require manual review and approval.
- **Version must match everywhere:** `pyproject.toml`, `__init__.py`, and the git tag must agree.

---

## Publish Workflow

The publish workflow (`.github/workflows/publish-pypi.yml`) triggers on:
- Tag push matching `v*.*.*`
- Manual `workflow_dispatch`

Before publishing, it:
1. Validates tag matches `pyproject.toml` and `__init__.py` versions.
2. Runs lint, type check, and test suite.
3. Builds sdist and wheel.
4. Verifies `.tcss` assets are included in the wheel.
5. Runs `twine check` on the distribution.
6. Publishes to PyPI via OIDC trusted publishing.

RC tags (`*-rc*`) are excluded from PyPI and published to TestPyPI instead.

---

## TestPyPI

RC releases go to TestPyPI via `.github/workflows/publish-testpypi.yml`.

To install from TestPyPI:
```bash
pip install --index-url https://test.pypi.org/simple/ atlasbridge
```

---

## Troubleshooting

### "File already exists" error on PyPI

If you manually published with `twine upload` before the GitHub Action ran, PyPI will reject the duplicate. Solutions:
- Do not manually publish. Let the tag-triggered workflow handle it.
- If you must publish manually, do not push the tag (or delete and re-push after fixing).

### CI is red on main

Do not tag until CI is green. Fix the failing check first. Publishing with a red CI risks shipping broken code.

### Version mismatch

The publish workflow validates that `pyproject.toml`, `__init__.py`, and the git tag all contain the same version string. If they don't match, the workflow fails with a clear error message.
