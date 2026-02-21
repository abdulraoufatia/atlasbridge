"""
Policy YAML parser — loads and validates AtlasBridge Policy DSL v0 and v1.

Usage::

    policy = load_policy("~/.atlasbridge/policy.yaml")  # returns Policy | PolicyV1
    policy = parse_policy(yaml_string)
    policy = default_policy()   # safe all-require_human default (v0)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from atlasbridge.core.policy.model import (
    AutonomyMode,
    MatchCriteria,
    Policy,
    PolicyDefaults,
    PolicyRule,
    RequireHumanAction,
)

if TYPE_CHECKING:
    from atlasbridge.core.policy.model_v1 import PolicyV1


class PolicyParseError(ValueError):
    """Raised when a policy file cannot be parsed or fails validation."""


def load_policy(path: str | Path, _visited: frozenset[str] | None = None) -> Policy | PolicyV1:
    """
    Load and validate a policy from a YAML file.

    Supports v0 (``policy_version: "0"``) and v1 (``policy_version: "1"``).
    v1 policies may use ``extends`` to inherit rules from a base file;
    cycle detection is enforced via ``_visited``.

    Args:
        path:      Path to the YAML policy file.
        _visited:  Internal — set of already-visited paths (cycle guard).

    Raises:
        PolicyParseError: if the file is missing, unreadable, or invalid.
    """
    p = Path(path).expanduser()
    if not p.exists():
        raise PolicyParseError(f"Policy file not found: {p}")
    try:
        content = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise PolicyParseError(f"Cannot read policy file {p}: {exc}") from exc

    visited = _visited or frozenset()
    return parse_policy(content, source=str(p), _visited=visited)


def parse_policy(
    yaml_text: str,
    source: str = "<string>",
    _visited: frozenset[str] | None = None,
) -> Policy | PolicyV1:
    """
    Parse and validate a YAML policy string.

    Dispatches to ``_parse_v0`` or ``_parse_v1`` based on the
    ``policy_version`` field in the YAML.

    Args:
        yaml_text: Raw YAML content.
        source:    Human-readable source label for error messages.
        _visited:  Internal — set of already-visited source paths (cycle guard).

    Returns:
        A validated :class:`Policy` (v0) or :class:`PolicyV1` (v1) instance.

    Raises:
        PolicyParseError: on YAML syntax errors or schema violations.
    """
    try:
        import yaml
    except ImportError as exc:
        raise PolicyParseError(
            "PyYAML is required for policy parsing. Install it with: pip install PyYAML"
        ) from exc

    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        raise PolicyParseError(f"YAML syntax error in {source}: {exc}") from exc

    if not isinstance(data, dict):
        raise PolicyParseError(
            f"Policy {source} must be a YAML mapping (got {type(data).__name__})"
        )

    visited = _visited or frozenset()

    # Pre-peek version before Pydantic — dispatch based on raw string
    version = str(data.get("policy_version", "")).strip()

    if version == "0":
        return _parse_v0(data, source)
    elif version == "1":
        return _parse_v1(data, source, visited)
    else:
        raise PolicyParseError(
            f"Policy {source}: unsupported policy_version {version!r}. "
            "Supported versions: '0', '1'."
        )


def _parse_v0(data: dict, source: str) -> Policy:
    """Parse and validate a v0 policy dict."""
    try:
        return Policy.model_validate(data)
    except ValidationError as exc:
        lines = [f"Policy validation failed in {source}:"]
        for err in exc.errors():
            loc = " → ".join(str(x) for x in err["loc"]) if err["loc"] else "(root)"
            lines.append(f"  {loc}: {err['msg']}")
        raise PolicyParseError("\n".join(lines)) from exc


def _parse_v1(
    data: dict,
    source: str,
    _visited: frozenset[str] = frozenset(),
) -> PolicyV1:
    """
    Parse and validate a v1 policy dict, resolving ``extends`` if present.

    Cycle detection: if ``extends`` points to a file already in ``_visited``,
    a ``PolicyParseError`` is raised.
    """
    from atlasbridge.core.policy.model_v1 import PolicyV1

    # Extract and resolve extends BEFORE Pydantic validation, so we can:
    # (a) detect cycles, (b) merge rules into the data dict
    extends_path_raw: str | None = data.get("extends")
    base: PolicyV1 | None = None

    if extends_path_raw:
        raw = Path(extends_path_raw).expanduser()
        # Resolve relative paths relative to the parent directory of the source file
        if not raw.is_absolute() and source != "<string>":
            raw = (Path(source).parent / raw).resolve()
        extends_path = str(raw)

        if extends_path in _visited or source in _visited and extends_path == source:
            raise PolicyParseError(
                f"Circular extends detected: {source!r} → {extends_path!r} "
                f"already in resolution chain {sorted(_visited)}"
            )

        try:
            base_raw = load_policy(extends_path, _visited=_visited | {source})
        except PolicyParseError as exc:
            raise PolicyParseError(
                f"Failed to load extended policy {extends_path!r} from {source}: {exc}"
            ) from exc

        if not isinstance(base_raw, PolicyV1):
            raise PolicyParseError(
                f"Policy {source}: extends target {extends_path!r} must be a v1 policy "
                f"(got policy_version={getattr(base_raw, 'policy_version', '?')!r})"
            )
        base = base_raw

    # Validate child policy (without merging extends yet — let model parse cleanly)
    try:
        child = PolicyV1.model_validate(data)
    except ValidationError as exc:
        lines = [f"Policy validation failed in {source}:"]
        for err in exc.errors():
            loc = " → ".join(str(x) for x in err["loc"]) if err["loc"] else "(root)"
            lines.append(f"  {loc}: {err['msg']}")
        raise PolicyParseError("\n".join(lines)) from exc

    # Merge base rules: child rules first (shadow base), base rules appended
    if base is not None:
        # Collect child rule IDs to skip duplicates from base
        child_ids = {r.id for r in child.rules}
        merged_rules = list(child.rules) + [r for r in base.rules if r.id not in child_ids]

        # Inherit defaults from base if child hasn't overridden them
        merged_defaults = child.defaults
        if child.defaults.model_dump() == PolicyDefaults().model_dump():
            merged_defaults = base.defaults

        child = PolicyV1(
            policy_version=child.policy_version,
            name=child.name,
            autonomy_mode=child.autonomy_mode,
            rules=merged_rules,
            defaults=merged_defaults,
            extends=child.extends,
        )

    return child


def default_policy() -> Policy:
    """
    Return the built-in safe-default policy (v0).

    All prompts are routed to human; no auto-replies.
    This is used when no policy file is configured.
    """
    return Policy(
        policy_version="0",
        name="safe-default",
        autonomy_mode=AutonomyMode.ASSIST,
        rules=[
            PolicyRule(
                id="default-require-human",
                description="Catch-all: route every prompt to the human operator.",
                match=MatchCriteria(),
                action=RequireHumanAction(
                    message="No policy file configured — all prompts require human input."
                ),
            )
        ],
        defaults=PolicyDefaults(no_match="require_human", low_confidence="require_human"),
    )


def validate_policy_file(path: str | Path) -> list[str]:
    """
    Validate a policy file and return a list of human-readable error strings.

    Returns an empty list if the policy is valid.
    """
    try:
        load_policy(path)
        return []
    except PolicyParseError as exc:
        return str(exc).splitlines()
