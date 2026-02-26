"""
Policy explain — full reasoning chain for any governance decision.

GA requirements:
  - Matched rule with full criteria
  - Failed rules with specific failure reasons
  - Risk assessment (score, category, factors)
  - Confidence traced to source signals
  - Alternative outcomes (what if confidence was different)
  - No secret leakage (all output redacted)
  - JSON output for tooling

Supports both v0 (Policy) and v1 (PolicyV1) policies.

Usage::

    output = explain_decision(decision)
    print(output)

    # Full explain with all rules, risk, and alternatives:
    result = full_explain(policy, prompt_text="Continue? [y/n]", ...)
    print(result.to_text())
    print(result.to_json())
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Union

from atlasbridge.core.policy.evaluator import (
    RuleMatchResult,
    _evaluate_rule,
    _evaluate_rule_v1,
    evaluate,
)
from atlasbridge.core.policy.model import Policy, PolicyDecision
from atlasbridge.core.security.redactor import redact as redact_secrets

if TYPE_CHECKING:
    from atlasbridge.core.policy.model_v1 import PolicyV1

AnyPolicy = Union[Policy, "PolicyV1"]


# ---------------------------------------------------------------------------
# Structured explain result
# ---------------------------------------------------------------------------


@dataclass
class RuleTrace:
    """Trace of a single rule evaluation."""

    rule_id: str
    description: str
    action_type: str
    matched: bool
    reasons: list[str]
    is_winner: bool = False


@dataclass
class AlternativeOutcome:
    """What would happen with a different confidence level."""

    confidence: str
    matched_rule_id: str | None
    action_type: str
    risk_score: int | None
    risk_category: str | None


@dataclass
class ExplainResult:
    """Full structured explain output for a policy evaluation."""

    # Policy context
    policy_name: str
    policy_version: str
    policy_hash: str

    # Input
    prompt_text: str
    prompt_type: str
    confidence: str
    tool_id: str
    repo: str
    session_tag: str

    # Decision
    matched_rule_id: str | None
    action_type: str
    action_value: str
    explanation: str

    # Risk
    risk_score: int | None = None
    risk_category: str | None = None
    risk_factors: list[dict[str, Any]] = field(default_factory=list)

    # Rule traces (all rules, not just matched)
    rule_traces: list[RuleTrace] = field(default_factory=list)

    # Alternative outcomes
    alternatives: list[AlternativeOutcome] = field(default_factory=list)

    def to_text(self) -> str:
        """Render as human-readable text for CLI output."""
        lines: list[str] = []
        lines.append("=" * 60)
        lines.append("POLICY EXPLAIN")
        lines.append("=" * 60)
        lines.append("")

        # Policy header
        lines.append(
            f"Policy: {self.policy_name!r}  "
            f"(version={self.policy_version}, hash={self.policy_hash})"
        )
        lines.append(
            f"Input:  prompt_type={self.prompt_type!r}  "
            f"confidence={self.confidence!r}  tool_id={self.tool_id!r}"
        )
        if self.repo:
            lines.append(f"        repo={self.repo!r}")
        if self.session_tag:
            lines.append(f"        session_tag={self.session_tag!r}")
        lines.append(f"        prompt_text={redact_secrets(self.prompt_text)!r}")
        lines.append("")

        # Decision
        lines.append("Decision:")
        lines.append(f"  Action:      {self.action_type.upper()}")
        if self.action_value:
            lines.append(f"  Reply value: {self.action_value!r}")
        lines.append(f"  Matched:     {self.matched_rule_id or '(none — default applied)'}")
        lines.append(f"  Explanation: {self.explanation}")
        lines.append("")

        # Risk assessment
        if self.risk_score is not None:
            lines.append("Risk Assessment:")
            lines.append(f"  Score:    {self.risk_score}/100 ({self.risk_category})")
            if self.risk_factors:
                lines.append("  Factors:")
                for f in self.risk_factors:
                    lines.append(f"    - {f['name']} (+{f['weight']}): {f['description']}")
            else:
                lines.append("  Factors:  (none)")
            lines.append("")

        # Rule traces
        lines.append(f"Rule Evaluation ({len(self.rule_traces)} rules):")
        lines.append("-" * 60)
        for i, trace in enumerate(self.rule_traces, 1):
            status = "MATCH" if trace.matched else "MISS "
            marker = "  << WINNER" if trace.is_winner else ""
            desc = f"  ({trace.description})" if trace.description else ""
            lines.append(f"  [{i}] Rule {trace.rule_id!r}{desc}")
            lines.append(f"      Result: {status}  Action: {trace.action_type}{marker}")
            for reason in trace.reasons:
                lines.append(f"      {reason}")
            lines.append("")

        # Alternative outcomes
        if self.alternatives:
            lines.append("Alternative Outcomes:")
            for alt in self.alternatives:
                risk_str = ""
                if alt.risk_score is not None:
                    risk_str = f"  risk={alt.risk_score}/100 ({alt.risk_category})"
                lines.append(
                    f"  confidence={alt.confidence!r}: "
                    f"rule={alt.matched_rule_id or '(default)'} "
                    f"action={alt.action_type}{risk_str}"
                )
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON output."""
        return {
            "policy": {
                "name": self.policy_name,
                "version": self.policy_version,
                "hash": self.policy_hash,
            },
            "input": {
                "prompt_text": redact_secrets(self.prompt_text),
                "prompt_type": self.prompt_type,
                "confidence": self.confidence,
                "tool_id": self.tool_id,
                "repo": self.repo,
                "session_tag": self.session_tag,
            },
            "decision": {
                "matched_rule_id": self.matched_rule_id,
                "action_type": self.action_type,
                "action_value": self.action_value,
                "explanation": self.explanation,
            },
            "risk": {
                "score": self.risk_score,
                "category": self.risk_category,
                "factors": self.risk_factors,
            },
            "rules": [
                {
                    "rule_id": t.rule_id,
                    "description": t.description,
                    "action_type": t.action_type,
                    "matched": t.matched,
                    "is_winner": t.is_winner,
                    "reasons": t.reasons,
                }
                for t in self.rule_traces
            ],
            "alternatives": [
                {
                    "confidence": a.confidence,
                    "matched_rule_id": a.matched_rule_id,
                    "action_type": a.action_type,
                    "risk_score": a.risk_score,
                    "risk_category": a.risk_category,
                }
                for a in self.alternatives
            ],
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Legacy explain functions (preserved for backward compatibility)
# ---------------------------------------------------------------------------


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

    # Risk assessment (GA)
    if decision.risk_score is not None:
        lines.append("")
        lines.append(f"Risk score:    {decision.risk_score}/100 ({decision.risk_category})")
        if decision.risk_factors:
            for f in decision.risk_factors:
                lines.append(f"  - {f['name']} (+{f['weight']}): {f['description']}")

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

    # Risk assessment (GA)
    if decision.risk_score is not None:
        lines.append("")
        lines.append(f"  Risk:        {decision.risk_score}/100 ({decision.risk_category})")
        if decision.risk_factors:
            for f in decision.risk_factors:
                lines.append(f"    - {f['name']} (+{f['weight']}): {f['description']}")

    lines.append("")
    lines.append("╚══ END DEBUG TRACE ══╝")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# GA full explain — structured output with all requirements
# ---------------------------------------------------------------------------


def full_explain(
    policy: AnyPolicy,
    prompt_text: str,
    prompt_type: str,
    confidence: str,
    tool_id: str = "*",
    repo: str = "",
    session_tag: str = "",
    session_state: str = "",
    channel_message: bool = False,
    branch: str = "",
    ci_status: str = "",
    file_scope: str = "",
    command_pattern: str = "",
    environment: str = "",
) -> ExplainResult:
    """
    Full GA explain: structured result with all rules, risk, and alternatives.

    For any decision, produces:
    - Matched rule with full criteria
    - ALL failed rules with specific failure reasons
    - Risk assessment (score, category, factors)
    - Alternative outcomes (what if confidence was different)
    - Secret-redacted output

    Returns an ExplainResult that can be rendered as text or JSON.
    """
    from atlasbridge.core.policy.model_v1 import PolicyV1

    use_v1 = isinstance(policy, PolicyV1)
    version = getattr(policy, "policy_version", "?")

    # Evaluate all rules (no short-circuit) to get full trace
    rule_traces: list[RuleTrace] = []
    first_match_id: str | None = None

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

        is_winner = result.matched and first_match_id is None
        if is_winner:
            first_match_id = rule.id

        rule_traces.append(
            RuleTrace(
                rule_id=rule.id,
                description=rule.description or "",
                action_type=rule.action.type,
                matched=result.matched,
                reasons=result.reasons,
                is_winner=is_winner,
            )
        )

    # Get actual decision (with risk)
    decision = evaluate(
        policy=policy,
        prompt_text=prompt_text,
        prompt_type=prompt_type,
        confidence=confidence,
        prompt_id="explain-prompt",
        session_id="explain-session",
        tool_id=tool_id,
        repo=repo,
        session_tag=session_tag,
        session_state=session_state,
        channel_message=channel_message,
        branch=branch,
        ci_status=ci_status,
        file_scope=file_scope,
        command_pattern=command_pattern,
        environment=environment,
    )

    # Compute alternative outcomes for different confidence levels
    alternatives: list[AlternativeOutcome] = []
    for alt_conf in ("low", "medium", "high"):
        if alt_conf == confidence:
            continue
        alt_decision = evaluate(
            policy=policy,
            prompt_text=prompt_text,
            prompt_type=prompt_type,
            confidence=alt_conf,
            prompt_id="explain-alt",
            session_id="explain-session",
            tool_id=tool_id,
            repo=repo,
            session_tag=session_tag,
            session_state=session_state,
            channel_message=channel_message,
            branch=branch,
            ci_status=ci_status,
            file_scope=file_scope,
            command_pattern=command_pattern,
            environment=environment,
        )
        alternatives.append(
            AlternativeOutcome(
                confidence=alt_conf,
                matched_rule_id=alt_decision.matched_rule_id,
                action_type=alt_decision.action_type,
                risk_score=alt_decision.risk_score,
                risk_category=alt_decision.risk_category,
            )
        )

    return ExplainResult(
        policy_name=policy.name,
        policy_version=version,
        policy_hash=policy.content_hash(),
        prompt_text=prompt_text,
        prompt_type=prompt_type,
        confidence=confidence,
        tool_id=tool_id,
        repo=repo,
        session_tag=session_tag,
        matched_rule_id=decision.matched_rule_id,
        action_type=decision.action_type,
        action_value=decision.action_value,
        explanation=decision.explanation,
        risk_score=decision.risk_score,
        risk_category=decision.risk_category,
        risk_factors=decision.risk_factors,
        rule_traces=rule_traces,
        alternatives=alternatives,
    )
