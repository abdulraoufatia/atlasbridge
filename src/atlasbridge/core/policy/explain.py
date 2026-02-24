"""
Policy explain — human-readable output for the ``atlasbridge policy test --explain`` command.

Supports both v0 (Policy) and v1 (PolicyV1) policies.

Usage::

    output = explain_decision(decision, policy)
    print(output)

    # Or explain all rules against a prompt:
    output = explain_policy(policy, prompt_text="Continue? [y/n]", ...)
    print(output)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Union

from atlasbridge.core.policy.evaluator import (
    RuleMatchResult,
    _evaluate_rule,
    _evaluate_rule_v1,
    evaluate,
)
from atlasbridge.core.policy.model import Policy, PolicyDecision

if TYPE_CHECKING:
    from atlasbridge.core.policy.model_v1 import PolicyV1

AnyPolicy = Union[Policy, "PolicyV1"]


def explain_decision(decision: PolicyDecision) -> str:
    """
    Format a PolicyDecision as a human-readable explanation.

    Returns a multi-line string suitable for CLI output.
    """
    lines: list[str] = []
    lines.append(f"Decision:      {decision.action_type.upper()}")
    if decision.action_value:
        lines.append(f"Reply value:   {decision.action_value!r}")
    lines.append(f"Matched rule:  {decision.matched_rule_id or '(none — default applied)'}")
    lines.append(f"Confidence:    {decision.confidence}")
    lines.append(f"Prompt type:   {decision.prompt_type}")
    lines.append(f"Autonomy mode: {decision.autonomy_mode}")
    lines.append(f"Policy hash:   {decision.policy_hash}")
    lines.append(f"Idem key:      {decision.idempotency_key}")
    lines.append("")
    lines.append(f"Explanation:   {decision.explanation}")
    return "\n".join(lines)


def explain_policy(
    policy: AnyPolicy,
    prompt_text: str,
    prompt_type: str,
    confidence: str,
    tool_id: str = "*",
    repo: str = "",
    session_tag: str = "",
    session_state: str = "",
    channel_message: bool = False,
) -> str:
    """
    Walk all rules in the policy and show which matched / failed, then show the final decision.

    This is the verbose mode used by ``atlasbridge policy test --explain``.
    Supports both v0 (Policy) and v1 (PolicyV1).
    """
    from atlasbridge.core.policy.model_v1 import PolicyV1

    use_v1 = isinstance(policy, PolicyV1)
    version = getattr(policy, "policy_version", "?")

    lines: list[str] = []
    lines.append(f"Policy: {policy.name!r}  (version={version}, hash={policy.content_hash()})")
    lines.append(
        f"Input:  prompt_type={prompt_type!r}  confidence={confidence!r}  tool_id={tool_id!r}"
    )
    if repo:
        lines.append(f"        repo={repo!r}")
    if session_tag:
        lines.append(f"        session_tag={session_tag!r}")
    if session_state:
        lines.append(f"        session_state={session_state!r}")
    if channel_message:
        lines.append(f"        channel_message={channel_message!r}")
    lines.append("")

    first_match: RuleMatchResult | None = None
    for rule in policy.rules:
        if use_v1:
            result = _evaluate_rule_v1(
                rule=rule,  # type: ignore[arg-type]
                prompt_type=prompt_type,
                confidence=confidence,
                excerpt=prompt_text,
                tool_id=tool_id,
                repo=repo,
                session_tag=session_tag,
                session_state=session_state,
                channel_message=channel_message,
            )
        else:
            result = _evaluate_rule(
                rule=rule,  # type: ignore[arg-type]
                prompt_type=prompt_type,
                confidence=confidence,
                excerpt=prompt_text,
                tool_id=tool_id,
                repo=repo,
            )

        status = "MATCH" if result.matched else "skip"
        lines.append(f"  Rule {rule.id!r:40s} [{status}]")
        for reason in result.reasons:
            lines.append(f"      {reason}")
        if result.matched and first_match is None:
            first_match = result
            lines.append(f"      → action: {rule.action.type}")
            lines.append("")
            lines.append("  (Remaining rules not evaluated — first match wins)")
            break
        lines.append("")

    if first_match is None:
        lines.append(f"  No rule matched → applying default ({policy.defaults.no_match})")

    return "\n".join(lines)


def debug_policy(
    policy: AnyPolicy,
    prompt_text: str,
    prompt_type: str,
    confidence: str,
    tool_id: str = "*",
    repo: str = "",
    session_tag: str = "",
    session_state: str = "",
    channel_message: bool = False,
) -> str:
    """
    Debug mode: evaluate ALL rules with full per-criterion trace (no short-circuit).

    Unlike ``explain_policy`` which stops at the first match and short-circuits
    failing criteria, this evaluates every criterion of every rule so authors
    can see exactly why each rule matched or failed.

    Output sections:
    1. Policy header + input parameters
    2. Per-rule trace with all criteria (no short-circuit)
    3. Final decision (same as normal evaluate())
    """
    from atlasbridge.core.policy.model_v1 import PolicyV1

    use_v1 = isinstance(policy, PolicyV1)
    version = getattr(policy, "policy_version", "?")

    lines: list[str] = []
    lines.append("╔══ POLICY DEBUG TRACE ══╗")
    lines.append("")
    lines.append(f"Policy: {policy.name!r}  (version={version}, hash={policy.content_hash()})")
    lines.append(
        f"Input:  prompt_type={prompt_type!r}  confidence={confidence!r}  tool_id={tool_id!r}"
    )
    if repo:
        lines.append(f"        repo={repo!r}")
    if session_tag:
        lines.append(f"        session_tag={session_tag!r}")
    if session_state:
        lines.append(f"        session_state={session_state!r}")
    if channel_message:
        lines.append(f"        channel_message={channel_message!r}")
    lines.append(f"        prompt_text={prompt_text!r}")
    lines.append("")
    lines.append(f"Rules: {len(policy.rules)} total")
    lines.append("─" * 60)

    first_match_id: str | None = None
    match_count = 0

    for idx, rule in enumerate(policy.rules, 1):
        if use_v1:
            result = _evaluate_rule_v1(
                rule=rule,  # type: ignore[arg-type]
                prompt_type=prompt_type,
                confidence=confidence,
                excerpt=prompt_text,
                tool_id=tool_id,
                repo=repo,
                session_tag=session_tag,
                session_state=session_state,
                channel_message=channel_message,
                short_circuit=False,
            )
        else:
            result = _evaluate_rule(
                rule=rule,  # type: ignore[arg-type]
                prompt_type=prompt_type,
                confidence=confidence,
                excerpt=prompt_text,
                tool_id=tool_id,
                repo=repo,
                short_circuit=False,
            )

        status = "MATCH" if result.matched else "MISS "
        marker = ""
        if result.matched:
            match_count += 1
            if first_match_id is None:
                first_match_id = rule.id  # type: ignore[attr-defined]
                marker = "  ← WINNER (first match)"

        desc = f"  ({rule.description})" if rule.description else ""  # type: ignore[attr-defined]
        lines.append(f"  [{idx}/{len(policy.rules)}] Rule {rule.id!r}{desc}")  # type: ignore[attr-defined]
        lines.append(f"       Result: {status}  Action: {rule.action.type}{marker}")  # type: ignore[attr-defined]
        for reason in result.reasons:
            lines.append(f"       {reason}")
        lines.append("")

    lines.append("─" * 60)
    lines.append(f"Summary: {match_count}/{len(policy.rules)} rules matched")
    if first_match_id:
        lines.append(f"Winner:  rule {first_match_id!r} (first-match-wins)")
    else:
        lines.append(f"Winner:  (none) → default: {policy.defaults.no_match}")
    lines.append("")

    # Show actual decision
    decision = evaluate(
        policy=policy,
        prompt_text=prompt_text,
        prompt_type=prompt_type,
        confidence=confidence,
        prompt_id="debug-prompt",
        session_id="debug-session",
        tool_id=tool_id,
        repo=repo,
        session_tag=session_tag,
        session_state=session_state,
        channel_message=channel_message,
    )
    lines.append("Final decision:")
    lines.append(f"  Action:      {decision.action_type.upper()}")
    if decision.action_value:
        lines.append(f"  Reply value: {decision.action_value!r}")
    lines.append(f"  Matched:     {decision.matched_rule_id or '(none — default applied)'}")
    lines.append(f"  Explanation: {decision.explanation}")
    lines.append("")
    lines.append("╚══ END DEBUG TRACE ══╝")

    return "\n".join(lines)
