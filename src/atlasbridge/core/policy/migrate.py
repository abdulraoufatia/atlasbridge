"""
Policy migration — upgrade AtlasBridge Policy DSL v0 → v1.

Usage::

    dest = migrate_v0_to_v1("~/.atlasbridge/policy.yaml")
    # or dry-run:
    new_content = migrate_v0_to_v1_text(text)
"""

from __future__ import annotations

from pathlib import Path


class MigrateError(ValueError):
    """Raised when migration fails (e.g. input is not a valid v0 policy)."""


def migrate_v0_to_v1_text(yaml_text: str) -> str:
    """
    Upgrade a v0 policy YAML string to v1 in memory.

    Performs a text-level substitution of ``policy_version: "0"`` →
    ``policy_version: "1"`` so that YAML comments are preserved.

    Args:
        yaml_text: Raw YAML content of a v0 policy.

    Returns:
        New YAML content with ``policy_version: "1"``.

    Raises:
        MigrateError: if the input does not contain a v0 version marker.
    """
    # We look for the literal YAML token, handling both single and double quotes
    import re

    pattern = r"""policy_version\s*:\s*["']0["']"""
    if not re.search(pattern, yaml_text):
        raise MigrateError(
            'Input does not contain a v0 policy_version marker (expected: policy_version: "0").'
        )

    # Replace the first occurrence; the validator will catch if it appears elsewhere
    new_text = re.sub(pattern, 'policy_version: "1"', yaml_text, count=1)
    return new_text


def migrate_v0_to_v1(
    source: str | Path,
    dest: str | Path | None = None,
) -> Path:
    """
    Upgrade a v0 policy file to v1, writing the result to ``dest`` (or in-place).

    - Rewrites ``policy_version: "0"`` → ``"1"`` (preserves all YAML comments)
    - Validates the result parses as PolicyV1
    - Returns the path written to

    Args:
        source: Path to the v0 policy file.
        dest:   Output path. If ``None``, overwrites ``source`` in place.

    Returns:
        The path that was written.

    Raises:
        MigrateError: if the source is unreadable, not a valid v0 policy, or
                      the migrated content fails PolicyV1 validation.
    """
    src = Path(source).expanduser()
    if not src.exists():
        raise MigrateError(f"Source policy file not found: {src}")

    try:
        original = src.read_text(encoding="utf-8")
    except OSError as exc:
        raise MigrateError(f"Cannot read {src}: {exc}") from exc

    # Validate the source parses as a v0 policy first
    from atlasbridge.core.policy.parser import PolicyParseError, parse_policy

    try:
        parse_policy(original, source=str(src))
    except PolicyParseError as exc:
        raise MigrateError(f"Source is not a valid v0 policy: {exc}") from exc

    # Perform text-level upgrade
    new_text = migrate_v0_to_v1_text(original)

    # Validate the migrated content parses as PolicyV1
    try:
        result = parse_policy(new_text, source=f"{src} (migrated)")
    except PolicyParseError as exc:
        raise MigrateError(f"Migrated content failed validation: {exc}") from exc

    from atlasbridge.core.policy.model_v1 import PolicyV1

    if not isinstance(result, PolicyV1):
        raise MigrateError(
            f"Unexpected parse result after migration: {type(result).__name__} (expected PolicyV1)"
        )

    # Write the result
    out_path = Path(dest).expanduser() if dest else src
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(new_text, encoding="utf-8")
    except OSError as exc:
        raise MigrateError(f"Cannot write to {out_path}: {exc}") from exc

    return out_path
