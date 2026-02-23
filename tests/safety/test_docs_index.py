"""Safety guard: every tracked docs/*.md file must appear in docs/README.md."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = ROOT / "docs"
DOCS_INDEX = DOCS_DIR / "README.md"


def _tracked_doc_files() -> list[Path]:
    """Return top-level docs/*.md files that are tracked in git (ignores local drafts)."""
    result = subprocess.run(
        ["git", "ls-files", "docs/*.md"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    if result.returncode != 0:
        # Fallback to filesystem scan if not in a git repo
        return sorted(DOCS_DIR.glob("*.md"))
    # Only include files directly in docs/, not subdirectories
    return [
        ROOT / f
        for f in result.stdout.strip().split("\n")
        if f and "/" not in f.removeprefix("docs/")
    ]


def test_docs_index_exists() -> None:
    """docs/README.md must exist."""
    assert DOCS_INDEX.is_file(), "docs/README.md is missing"


def test_all_docs_linked_in_index() -> None:
    """Every tracked .md file in docs/ must be referenced in docs/README.md."""
    index_text = DOCS_INDEX.read_text(encoding="utf-8")
    doc_files = _tracked_doc_files()

    unlinked = []
    for doc in doc_files:
        if doc.name == "README.md":
            continue
        if doc.name not in index_text:
            unlinked.append(doc.name)

    assert not unlinked, (
        f"The following docs are not linked in docs/README.md: {unlinked}. "
        "Add them to the Documentation Map table."
    )


def test_no_broken_doc_links_in_index() -> None:
    """Every .md link in docs/README.md must point to an existing file."""
    import re

    index_text = DOCS_INDEX.read_text(encoding="utf-8")
    # Match markdown links like [text](filename.md) — only local .md files
    links = re.findall(r"\]\(([a-zA-Z0-9_-]+\.md)\)", index_text)

    broken = []
    for link in links:
        if not (DOCS_DIR / link).is_file():
            broken.append(link)

    assert not broken, f"Broken links in docs/README.md: {broken}"
