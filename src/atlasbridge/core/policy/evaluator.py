"""
Policy evaluator — deterministic first-match-wins rule engine.

Supports both v0 (Policy) and v1 (PolicyV1) policies.

Usage::

    decision = evaluate(
        policy=policy,
        prompt_text="Continue? [y/n]",
        prompt_type="yes_no",
        confidence="high",
        prompt_id="abc123",
        session_id="xyz789",
        tool_id="claude_code",
        repo="/home/user/project",
        session_tag="ci",          # v1 only
    )
"""

from __future__ import annotations

import re
import signal
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

import structlog

from atlasbridge.core.policy.model import (
    ConfidenceLevel,
    DenyAction,
    Policy,
    PolicyDecision,
    PolicyRule,
    PromptTypeFilter,
    RequireHumanAction,
    confidence_from_str,
)
from atlasbridge.core.risk import RiskClassifier, RiskInput

if TYPE_CHECKING:
    from atlasbridge.core.policy.model_v1 import MatchCriteriaV1, PolicyRuleV1, PolicyV1

logger = structlog.get_logger()

_REGEX_TIMEOUT_S = 0.1  # 100ms max per regex evaluation


# ---------------------------------------------------------------------------
# Timeout context manager (UNIX only; Windows silently skips)
# ---------------------------------------------------------------------------


@contextmanager
def _regex_timeout(seconds: float) -> Iterator[None]:
    """Raise TimeoutError if the block runs longer than `seconds`."""
    try:
        signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError()))
        signal.setitimer(signal.ITIMER_REAL, seconds)
        yield
    except AttributeError:
        # Windows — no SIGALRM; skip timeout enforcement
        yield
    finally:
        try:
            signal.setitimer(signal.ITIMER_REAL, 0)
        except AttributeError:
            pass


# ---------------------------------------------------------------------------
# Per-criterion matching helpers
# ---------------------------------------------------------------------------


def _match_tool_id(criterion: str, tool_id: str) -> tuple[bool, str]:
    if criterion == "*":
        return True, "tool_id: * (wildcard, always matches)"
    matched = criterion == tool_id
    return matched, f"tool_id: {criterion!r} {'==' if matched else '!='} {tool_id!r}"


def _match_repo(criterion: str | None, repo: str) -> tuple[bool, str]:
    if criterion is None:
        return True, "repo: not specified (always matches)"
    matched = repo.startswith(criterion)
    return (
        matched,
        f"repo: {repo!r} {'starts with' if matched else 'does not start with'} {criterion!r}",
    )


def _match_prompt_type(
    criterion: list[PromptTypeFilter] | None, prompt_type: str
) -> tuple[bool, str]:
    if criterion is None:
        return True, "prompt_type: not specified (always matches)"
    # ANY in list → always matches
    if PromptTypeFilter.ANY in criterion:
        return True, "prompt_type: * (wildcard, always matches)"
    matched = any(f.value == prompt_type for f in criterion)
    types_str = [f.value for f in criterion]
    return (
        matched,
        f"prompt_type: {prompt_type!r} {'in' if matched else 'not in'} {types_str}",
    )


def _match_confidence(min_confidence: ConfidenceLevel, confidence_str: str) -> tuple[bool, str]:
    event_level = confidence_from_str(confidence_str)
    matched = event_level >= min_confidence
    return (
        matched,
        f"min_confidence: {confidence_str} {'≥' if matched else '<'} {min_confidence.value}",
    )


def _match_max_confidence(
    max_confidence: ConfidenceLevel | None, confidence_str: str
) -> tuple[bool, str]:
    if max_confidence is None:
        return True, "max_confidence: not specified (always matches)"
    event_level = confidence_from_str(confidence_str)
    matched = event_level <= max_confidence
    return (
        matched,
        f"max_confidence: {confidence_str} {'≤' if matched else '>'} {max_confidence.value}",
    )


def _match_session_tag(criterion: str | None, session_tag: str) -> tuple[bool, str]:
    if criterion is None:
        return True, "session_tag: not specified (always matches)"
    matched = criterion == session_tag
    return (
        matched,
        f"session_tag: {session_tag!r} {'==' if matched else '!='} {criterion!r}",
    )


def _match_session_state(criterion: list[str] | None, session_state: str) -> tuple[bool, str]:
    if criterion is None:
        return True, "session_state: not specified (always matches)"
    if not session_state:
        return False, f"session_state: no state provided, required one of {criterion}"
    matched = session_state in criterion
    return (
        matched,
        f"session_state: {session_state!r} {'in' if matched else 'not in'} {criterion}",
    )


def _match_channel_message(criterion: bool | None, channel_message: bool) -> tuple[bool, str]:
    if criterion is None:
        return True, "channel_message: not specified (always matches)"
    matched = criterion == channel_message
    return (
        matched,
        f"channel_message: {criterion!r} {'==' if matched else '!='} {channel_message!r}",
    )


def _match_environment(criterion: str | None, environment: str) -> tuple[bool, str]:
    if criterion is None:
        return True, "environment: not specified (always matches)"
    if criterion == environment:
        return True, f"environment: {criterion!r} == {environment!r}"
    return False, f"environment: {criterion!r} != {environment!r}"


def _match_deny_input_types(criterion: list[str] | None, prompt_type: str) -> tuple[bool, str]:
    if criterion is None:
        return True, "deny_input_types: not specified (always matches)"
    matched = prompt_type in criterion
    return (
        matched,
        f"deny_input_types: {prompt_type!r} {'in' if matched else 'not in'} {criterion}",
    )


def _match_tool_name(
    criterion: str | None,
    excerpt: str,
    is_regex: bool = False,
) -> tuple[bool, str]:
    """Match on a tool_name field. Extracts tool name from 'tool_use: <name>(...)' excerpts."""
    if criterion is None:
        return True, "tool_name: not specified (always matches)"

    # Extract tool name from synthetic excerpt format: "tool_use: name({args})"
    tool_name = excerpt
    if excerpt.startswith("tool_use: "):
        paren_idx = excerpt.find("(", 10)
        if paren_idx > 0:
            tool_name = excerpt[10:paren_idx]
        else:
            tool_name = excerpt[10:]

    if is_regex:
        try:
            with _regex_timeout(_REGEX_TIMEOUT_S):
                matched = bool(re.search(criterion, tool_name, re.IGNORECASE))
            return (
                matched,
                f"tool_name: regex {criterion!r} {'matched' if matched else 'did not match'} "
                f"{tool_name!r}",
            )
        except (TimeoutError, re.error):
            return False, f"tool_name: regex {criterion!r} failed"

    matched = criterion.lower() == tool_name.lower()
    return (
        matched,
        f"tool_name: {criterion!r} {'==' if matched else '!='} {tool_name!r}",
    )


def _match_contains(
    contains: str | None,
    contains_is_regex: bool,
    excerpt: str,
) -> tuple[bool, str]:
    if contains is None:
        return True, "contains: not specified (always matches)"

    if not contains_is_regex:
        matched = contains.lower() in excerpt.lower()
        return (
            matched,
            f"contains: substring {contains!r} {'found' if matched else 'not found'} in excerpt",
        )

    # Regex match with timeout
    try:
        with _regex_timeout(_REGEX_TIMEOUT_S):
            compiled = re.compile(contains, re.IGNORECASE | re.DOTALL)
            matched = bool(compiled.search(excerpt))
        return (
            matched,
            f"contains: regex {contains!r} {'matched' if matched else 'did not match'} excerpt",
        )
    except TimeoutError:
        logger.warning("regex_timeout", pattern=contains)
        return False, f"contains: regex {contains!r} timed out — rule skipped"
    except re.error as exc:
        logger.warning("regex_error", pattern=contains, error=str(exc))
        return False, f"contains: regex error {exc} — rule skipped"


# ---------------------------------------------------------------------------
# Single-rule evaluation
# ---------------------------------------------------------------------------


class RuleMatchResult:
    """Result of evaluating one rule against a prompt."""

    __slots__ = ("rule_id", "matched", "reasons")

    def __init__(self, rule_id: str, matched: bool, reasons: list[str]) -> None:
        self.rule_id = rule_id
        self.matched = matched
        self.reasons = reasons


def _evaluate_rule(
    rule: PolicyRule,
    prompt_type: str,
    confidence: str,
    excerpt: str,
    tool_id: str,
    repo: str,
    short_circuit: bool = True,
) -> RuleMatchResult:
    """Evaluate a single v0 rule. Returns RuleMatchResult with per-criterion reasons."""
    m = rule.match
    reasons: list[str] = []

    checks = [
        _match_tool_id(m.tool_id, tool_id),
        _match_repo(m.repo, repo),
        _match_prompt_type(m.prompt_type, prompt_type),
        _match_confidence(m.min_confidence, confidence),
        _match_tool_name(m.tool_name, excerpt, m.contains_is_regex),
        _match_contains(m.contains, m.contains_is_regex, excerpt),
    ]

    all_pass = True
    for ok, reason in checks:
        reasons.append(("✓ " if ok else "✗ ") + reason)
        if not ok:
            all_pass = False
            if short_circuit:
                break

    return RuleMatchResult(rule_id=rule.id, matched=all_pass, reasons=reasons)


def _eval_criteria_block(
    m: MatchCriteriaV1,
    prompt_type: str,
    confidence: str,
    excerpt: str,
    tool_id: str,
    repo: str,
    session_tag: str,
    session_state: str = "",
    channel_message: bool = False,
    environment: str = "",
    short_circuit: bool = True,
) -> tuple[bool, list[str]]:
    """
    Evaluate a MatchCriteriaV1 block (flat OR any_of), returning (matched, reasons).

    Used internally by _evaluate_rule_v1 and for any_of/none_of sub-blocks.
    Does NOT evaluate none_of (callers handle that separately at the rule level).
    """
    reasons: list[str] = []

    if m.any_of is not None:
        # OR semantics: match if ANY sub-block passes
        any_matched = False
        for i, sub in enumerate(m.any_of):
            sub_matched, sub_reasons = _eval_criteria_block(
                sub,
                prompt_type,
                confidence,
                excerpt,
                tool_id,
                repo,
                session_tag,
                session_state,
                channel_message,
                environment=environment,
                short_circuit=short_circuit,
            )
            reasons.append(f"any_of[{i}]: {'✓ matched' if sub_matched else '✗ no match'}")
            for r in sub_reasons:
                reasons.append(f"  {r}")
            if sub_matched:
                if short_circuit:
                    return True, reasons
                any_matched = True
        return any_matched, reasons

    # Flat AND checks
    checks = [
        _match_tool_id(m.tool_id, tool_id),
        _match_repo(m.repo, repo),
        _match_prompt_type(m.prompt_type, prompt_type),
        _match_confidence(m.min_confidence, confidence),
        _match_max_confidence(m.max_confidence, confidence),
        _match_contains(m.contains, m.contains_is_regex, excerpt),
        _match_session_tag(m.session_tag, session_tag),
        _match_session_state(m.session_state, session_state),
        _match_channel_message(m.channel_message, channel_message),
        _match_deny_input_types(m.deny_input_types, prompt_type),
        _match_environment(m.environment, environment),
    ]

    all_pass = True
    for ok, reason in checks:
        reasons.append(("✓ " if ok else "✗ ") + reason)
        if not ok:
            all_pass = False
            if short_circuit:
                break

    return all_pass, reasons


def _evaluate_rule_v1(
    rule: PolicyRuleV1,
    prompt_type: str,
    confidence: str,
    excerpt: str,
    tool_id: str,
    repo: str,
    session_tag: str,
    session_state: str = "",
    channel_message: bool = False,
    environment: str = "",
    short_circuit: bool = True,
) -> RuleMatchResult:
    """
    Evaluate a single v1 rule.

    Evaluation order:
    1. Flat AND criteria (or any_of OR block) — primary match condition
    2. none_of NOT filter — fail if any sub-block matches
    """
    m = rule.match
    reasons: list[str] = []

    # Step 1: primary match (flat AND or any_of)
    primary_matched, primary_reasons = _eval_criteria_block(
        m,
        prompt_type,
        confidence,
        excerpt,
        tool_id,
        repo,
        session_tag,
        session_state,
        channel_message,
        environment=environment,
        short_circuit=short_circuit,
    )
    reasons.extend(primary_reasons)

    if not primary_matched:
        if short_circuit:
            return RuleMatchResult(rule_id=rule.id, matched=False, reasons=reasons)
        # In debug mode, continue evaluating none_of for full trace
        reasons.append("  (primary criteria failed — none_of shown for completeness)")

    # Step 2: none_of NOT filter
    excluded = False
    if m.none_of is not None:
        for i, sub in enumerate(m.none_of):
            sub_matched, sub_reasons = _eval_criteria_block(
                sub,
                prompt_type,
                confidence,
                excerpt,
                tool_id,
                repo,
                session_tag,
                session_state,
                channel_message,
                environment=environment,
                short_circuit=short_circuit,
            )
            if sub_matched:
                excluded = True
                reasons.append(f"✗ none_of[{i}]: matched (excluded by NOT condition)")
                for r in sub_reasons:
                    reasons.append(f"  {r}")
                if short_circuit:
                    return RuleMatchResult(rule_id=rule.id, matched=False, reasons=reasons)
            else:
                reasons.append(f"✓ none_of[{i}]: did not match (NOT condition satisfied)")

    final_matched = primary_matched and not excluded
    return RuleMatchResult(rule_id=rule.id, matched=final_matched, reasons=reasons)


# ---------------------------------------------------------------------------
# Top-level evaluate()
# ---------------------------------------------------------------------------


def _compute_risk(
    prompt_type: str,
    action_type: str,
    confidence: str,
    branch: str = "",
    ci_status: str = "",
    file_scope: str = "",
    command_pattern: str = "",
    environment: str = "",
) -> tuple[int, str, list[dict]]:
    """Compute risk assessment and return (score, category, factors_list)."""
    assessment = RiskClassifier.classify(
        RiskInput(
            prompt_type=prompt_type,
            action_type=action_type,
            confidence=confidence,
            branch=branch,
            ci_status=ci_status,
            file_scope=file_scope,
            command_pattern=command_pattern,
            environment=environment,
        )
    )
    factors = [
        {"name": f.name, "weight": f.weight, "description": f.description}
        for f in assessment.factors
    ]
    return assessment.score, assessment.category.value, factors


def evaluate(
    policy: Policy | PolicyV1,
    prompt_text: str,
    prompt_type: str,
    confidence: str,
    prompt_id: str,
    session_id: str,
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
) -> PolicyDecision:
    """
    Evaluate the policy against a prompt event. First-match-wins.

    Dispatches to v0 or v1 evaluation based on the policy type.
    Computes a deterministic risk assessment for every decision.

    Args:
        policy:       Validated Policy (v0) or PolicyV1 (v1) instance.
        prompt_text:  The prompt excerpt (as seen by the user).
        prompt_type:  PromptType string value (e.g. "yes_no").
        confidence:   Confidence string (e.g. "high", "medium", "low").
        prompt_id:    Unique ID of the PromptEvent.
        session_id:   Session the prompt belongs to.
        tool_id:      Adapter/tool name (e.g. "claude_code").
        repo:         Working directory of the session.
        session_tag:  Session label (v1 only; used for session_tag rule matching).
        session_state: Current conversation state (v1 only; e.g. "idle", "running").
        channel_message: Whether message originated from a channel (v1 only).
        branch:       Git branch name (for risk classification).
        ci_status:    CI status: passing, failing, unknown, "" (for risk classification).
        file_scope:   File sensitivity: general, config, infrastructure, secrets.
        command_pattern: Command text for destructive pattern detection.
        environment:  Runtime environment: dev, staging, production.

    Returns:
        :class:`PolicyDecision` with matched rule, action, explanation, and risk assessment.
    """
    from atlasbridge.core.policy.model_v1 import PolicyV1

    policy_hash = policy.content_hash()
    autonomy_mode = policy.autonomy_mode.value

    use_v1 = isinstance(policy, PolicyV1)

    # Evaluate rules in order — first match wins
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
                environment=environment,
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

        if result.matched:
            explanation = (
                f"Rule {rule.id!r} matched"
                + (f" — {rule.description}" if rule.description else "")
                + ": "
                + "; ".join(
                    r.lstrip("✓ ").lstrip("✗ ") for r in result.reasons if r.startswith("✓")
                )
            )
            risk_score, risk_cat, risk_factors = _compute_risk(
                prompt_type=prompt_type,
                action_type=rule.action.type,
                confidence=confidence,
                branch=branch,
                ci_status=ci_status,
                file_scope=file_scope,
                command_pattern=command_pattern,
                environment=environment,
            )
            logger.debug(
                "policy_match",
                rule_id=rule.id,
                action=rule.action.type,
                risk_score=risk_score,
                risk_category=risk_cat,
            )
            return PolicyDecision(
                prompt_id=prompt_id,
                session_id=session_id,
                policy_hash=policy_hash,
                matched_rule_id=rule.id,
                action=rule.action,
                explanation=explanation,
                confidence=confidence,
                prompt_type=prompt_type,
                autonomy_mode=autonomy_mode,
                risk_score=risk_score,
                risk_category=risk_cat,
                risk_factors=risk_factors,
            )

    # No rule matched — apply defaults
    conf_level = confidence_from_str(confidence)
    if conf_level == ConfidenceLevel.LOW:
        fallback = policy.defaults.low_confidence
        explanation = f"No rule matched and confidence is LOW — applying default: {fallback}"
    else:
        fallback = policy.defaults.no_match
        explanation = f"No rule matched — applying default: {fallback}"

    fallback_action: DenyAction | RequireHumanAction
    if fallback == "deny":
        fallback_action = DenyAction(reason="No policy rule matched (default: deny)")
    else:
        fallback_action = RequireHumanAction(
            message="No policy rule matched — human input required"
        )

    risk_score, risk_cat, risk_factors = _compute_risk(
        prompt_type=prompt_type,
        action_type=fallback_action.type,
        confidence=confidence,
        branch=branch,
        ci_status=ci_status,
        file_scope=file_scope,
        command_pattern=command_pattern,
        environment=environment,
    )
    logger.debug("policy_no_match", fallback=fallback, risk_score=risk_score)
    return PolicyDecision(
        prompt_id=prompt_id,
        session_id=session_id,
        policy_hash=policy_hash,
        matched_rule_id=None,
        action=fallback_action,
        explanation=explanation,
        confidence=confidence,
        prompt_type=prompt_type,
        autonomy_mode=autonomy_mode,
        risk_score=risk_score,
        risk_category=risk_cat,
        risk_factors=risk_factors,
    )
