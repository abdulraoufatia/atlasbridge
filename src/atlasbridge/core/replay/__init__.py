"""
Deterministic session replay engine.

Re-evaluates all governance decisions from a recorded session against
the original (or an alternative) policy.  Produces a ReplayReport showing:
  - Each prompt event re-evaluated with the same inputs
  - Whether the decision would be identical or different
  - A diff of changed decisions (rule, action, risk)

This is audit-log replay (re-evaluation), not PTY re-execution.
Given identical inputs and governance state, the engine produces
identical output — this is the core determinism guarantee.

Invariants:
  - Replay NEVER mutates the audit log
  - Replay NEVER triggers channel notifications
  - Replay NEVER modifies session state
  - Same policy + same inputs = same decisions (hash-verified)

Usage::

    engine = ReplayEngine(db)
    snapshot = engine.load_session("session-123")
    report = engine.replay(snapshot)
    assert report.is_identical  # same policy → identical decisions

    # Policy diff mode:
    report = engine.replay(snapshot, alt_policy=new_policy)
    for diff in report.diffs:
        print(diff)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Union

from atlasbridge.core.policy.evaluator import evaluate
from atlasbridge.core.policy.model import Policy

if TYPE_CHECKING:
    from atlasbridge.core.policy.model_v1 import PolicyV1

AnyPolicy = Union[Policy, "PolicyV1"]


# ---------------------------------------------------------------------------
# Session snapshot — captured governance state
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PromptSnapshot:
    """A single prompt event from a recorded session."""

    prompt_id: str
    prompt_type: str
    confidence: str
    excerpt: str
    status: str
    response_normalized: str
    channel_identity: str
    created_at: str


@dataclass(frozen=True)
class SessionSnapshot:
    """Complete governance state of a recorded session."""

    session_id: str
    tool: str
    command: list[str]
    cwd: str
    label: str
    status: str
    started_at: str
    ended_at: str
    prompts: tuple[PromptSnapshot, ...]

    @property
    def prompt_count(self) -> int:
        return len(self.prompts)

    def content_hash(self) -> str:
        """SHA-256 hash of the snapshot content for verification."""
        data = json.dumps(
            {
                "session_id": self.session_id,
                "tool": self.tool,
                "command": self.command,
                "cwd": self.cwd,
                "prompts": [
                    {
                        "prompt_id": p.prompt_id,
                        "prompt_type": p.prompt_type,
                        "confidence": p.confidence,
                        "excerpt": p.excerpt,
                        "status": p.status,
                        "response_normalized": p.response_normalized,
                    }
                    for p in self.prompts
                ],
            },
            sort_keys=True,
        )
        return hashlib.sha256(data.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Replay decision and diff
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReplayDecision:
    """Result of re-evaluating a single prompt."""

    prompt_id: str
    prompt_type: str
    confidence: str

    # Original decision (from session record)
    original_status: str
    original_response: str

    # Replayed decision
    matched_rule_id: str | None
    action_type: str
    action_value: str
    risk_score: int | None
    risk_category: str | None
    explanation: str


@dataclass(frozen=True)
class DecisionDiff:
    """A difference between the original and replayed decision."""

    prompt_id: str
    prompt_type: str
    field: str  # "matched_rule_id", "action_type", "action_value", "risk_category"
    original: str
    replayed: str


@dataclass
class ReplayReport:
    """Complete replay result for a session."""

    session_id: str
    snapshot_hash: str
    policy_hash: str
    policy_name: str
    prompt_count: int

    decisions: list[ReplayDecision] = field(default_factory=list)
    diffs: list[DecisionDiff] = field(default_factory=list)

    @property
    def is_identical(self) -> bool:
        """True if replay produced zero diffs (governance invariant holds)."""
        return len(self.diffs) == 0

    @property
    def diff_count(self) -> int:
        return len(self.diffs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "snapshot_hash": self.snapshot_hash,
            "policy_hash": self.policy_hash,
            "policy_name": self.policy_name,
            "prompt_count": self.prompt_count,
            "is_identical": self.is_identical,
            "diff_count": self.diff_count,
            "decisions": [
                {
                    "prompt_id": d.prompt_id,
                    "prompt_type": d.prompt_type,
                    "confidence": d.confidence,
                    "matched_rule_id": d.matched_rule_id,
                    "action_type": d.action_type,
                    "risk_score": d.risk_score,
                    "risk_category": d.risk_category,
                }
                for d in self.decisions
            ],
            "diffs": [
                {
                    "prompt_id": d.prompt_id,
                    "field": d.field,
                    "original": d.original,
                    "replayed": d.replayed,
                }
                for d in self.diffs
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def to_text(self) -> str:
        """Render as human-readable text for CLI output."""
        lines: list[str] = []
        lines.append("=" * 60)
        lines.append("SESSION REPLAY REPORT")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"Session:       {self.session_id}")
        lines.append(f"Snapshot hash: {self.snapshot_hash}")
        lines.append(f"Policy:        {self.policy_name} ({self.policy_hash})")
        lines.append(f"Prompts:       {self.prompt_count}")
        lines.append(f"Identical:     {'YES' if self.is_identical else 'NO'}")
        lines.append(f"Diffs:         {self.diff_count}")
        lines.append("")

        if self.decisions:
            lines.append("Decisions:")
            lines.append("-" * 60)
            for d in self.decisions:
                risk_str = ""
                if d.risk_score is not None:
                    risk_str = f" risk={d.risk_score}/100({d.risk_category})"
                lines.append(
                    f"  [{d.prompt_id[:8]}] {d.prompt_type} "
                    f"conf={d.confidence} → "
                    f"rule={d.matched_rule_id or '(default)'} "
                    f"action={d.action_type}{risk_str}"
                )
            lines.append("")

        if self.diffs:
            lines.append("DIFFERENCES:")
            lines.append("-" * 60)
            for dd in self.diffs:
                lines.append(
                    f"  [{dd.prompt_id[:8]}] {dd.field}: {dd.original!r} → {dd.replayed!r}"
                )
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Replay engine
# ---------------------------------------------------------------------------


class ReplayEngine:
    """Deterministic session replay engine.

    Loads a session snapshot from the database and re-evaluates all prompts
    against a policy.  Zero side effects — read-only.
    """

    def __init__(self, db: Any) -> None:
        self._db = db

    def load_session(self, session_id: str) -> SessionSnapshot:
        """Load a session and all its prompts from the database.

        Raises ValueError if session not found.
        """
        session = self._db.get_session(session_id)
        if session is None:
            raise ValueError(f"Session {session_id!r} not found")

        prompt_rows = self._db.list_prompts_for_session(session_id)
        prompts = tuple(
            PromptSnapshot(
                prompt_id=row["id"],
                prompt_type=row["prompt_type"],
                confidence=row["confidence"],
                excerpt=row["excerpt"] or "",
                status=row["status"],
                response_normalized=row["response_normalized"] or "",
                channel_identity=row["channel_identity"] or "",
                created_at=row["created_at"] or "",
            )
            for row in prompt_rows
        )

        command_raw = session["command"] or "[]"
        try:
            command = json.loads(command_raw)
        except (json.JSONDecodeError, TypeError):
            command = [str(command_raw)]

        return SessionSnapshot(
            session_id=session["id"],
            tool=session["tool"] or "",
            command=command,
            cwd=session["cwd"] or "",
            label=session["label"] or "",
            status=session["status"] or "",
            started_at=session["started_at"] or "",
            ended_at=session["ended_at"] or "",
            prompts=prompts,
        )

    def replay(
        self,
        snapshot: SessionSnapshot,
        policy: AnyPolicy | None = None,
        *,
        branch: str = "",
        ci_status: str = "",
        file_scope: str = "",
        environment: str = "",
    ) -> ReplayReport:
        """Re-evaluate all prompts in the snapshot against a policy.

        If no policy is provided, uses a minimal default policy that
        routes everything to human — useful for verifying the snapshot
        structure without needing the original policy file.

        Args:
            snapshot: Session snapshot to replay.
            policy: Policy to evaluate against. If None, uses default.
            branch: Git branch context for risk classification.
            ci_status: CI status for risk classification.
            file_scope: File sensitivity scope.
            environment: Runtime environment context.

        Returns:
            ReplayReport with all decisions and any diffs.
        """
        if policy is None:
            policy = Policy(
                policy_version="0",
                name="replay-default",
                rules=[],
            )

        report = ReplayReport(
            session_id=snapshot.session_id,
            snapshot_hash=snapshot.content_hash(),
            policy_hash=policy.content_hash(),
            policy_name=policy.name,
            prompt_count=snapshot.prompt_count,
        )

        for prompt in snapshot.prompts:
            decision = evaluate(
                policy=policy,
                prompt_text=prompt.excerpt,
                prompt_type=prompt.prompt_type,
                confidence=prompt.confidence,
                prompt_id=prompt.prompt_id,
                session_id=snapshot.session_id,
                tool_id=snapshot.tool,
                repo=snapshot.cwd,
                branch=branch,
                ci_status=ci_status,
                file_scope=file_scope,
                environment=environment,
            )

            replay_decision = ReplayDecision(
                prompt_id=prompt.prompt_id,
                prompt_type=prompt.prompt_type,
                confidence=prompt.confidence,
                original_status=prompt.status,
                original_response=prompt.response_normalized,
                matched_rule_id=decision.matched_rule_id,
                action_type=decision.action_type,
                action_value=decision.action_value,
                risk_score=decision.risk_score,
                risk_category=decision.risk_category,
                explanation=decision.explanation,
            )
            report.decisions.append(replay_decision)

            # Detect diffs between original outcome and replayed decision
            # Compare action_type against original status
            # (original status is prompt status like "resolved", "expired" etc.
            #  so we compare the replayed action_type which tells us what
            #  the policy would *recommend*)
            self._detect_diffs(prompt, decision, report)

        return report

    def replay_diff(
        self,
        snapshot: SessionSnapshot,
        original_policy: AnyPolicy,
        alt_policy: AnyPolicy,
        **kwargs: Any,
    ) -> ReplayReport:
        """Compare two policies against the same session.

        Returns a ReplayReport where diffs show differences between
        the two policies' decisions (not original vs replayed).
        """
        original_report = self.replay(snapshot, original_policy, **kwargs)
        alt_report = self.replay(snapshot, alt_policy, **kwargs)

        diff_report = ReplayReport(
            session_id=snapshot.session_id,
            snapshot_hash=snapshot.content_hash(),
            policy_hash=alt_policy.content_hash(),
            policy_name=f"{original_policy.name} vs {alt_policy.name}",
            prompt_count=snapshot.prompt_count,
            decisions=alt_report.decisions,
        )

        # Compare decisions between the two policies
        for orig_d, alt_d in zip(original_report.decisions, alt_report.decisions, strict=True):
            if orig_d.matched_rule_id != alt_d.matched_rule_id:
                diff_report.diffs.append(
                    DecisionDiff(
                        prompt_id=orig_d.prompt_id,
                        prompt_type=orig_d.prompt_type,
                        field="matched_rule_id",
                        original=str(orig_d.matched_rule_id),
                        replayed=str(alt_d.matched_rule_id),
                    )
                )
            if orig_d.action_type != alt_d.action_type:
                diff_report.diffs.append(
                    DecisionDiff(
                        prompt_id=orig_d.prompt_id,
                        prompt_type=orig_d.prompt_type,
                        field="action_type",
                        original=orig_d.action_type,
                        replayed=alt_d.action_type,
                    )
                )
            if orig_d.action_value != alt_d.action_value:
                diff_report.diffs.append(
                    DecisionDiff(
                        prompt_id=orig_d.prompt_id,
                        prompt_type=orig_d.prompt_type,
                        field="action_value",
                        original=orig_d.action_value,
                        replayed=alt_d.action_value,
                    )
                )
            if orig_d.risk_category != alt_d.risk_category:
                diff_report.diffs.append(
                    DecisionDiff(
                        prompt_id=orig_d.prompt_id,
                        prompt_type=orig_d.prompt_type,
                        field="risk_category",
                        original=str(orig_d.risk_category),
                        replayed=str(alt_d.risk_category),
                    )
                )

        return diff_report

    @staticmethod
    def _detect_diffs(
        prompt: PromptSnapshot,
        decision: Any,
        report: ReplayReport,
    ) -> None:
        """Compare a replayed decision against original prompt record."""
        # Map prompt status to expected action type
        # resolved/reply_received → the prompt was answered
        # expired → TTL elapsed
        # The replayed action_type tells us what the policy *would* do
        #
        # We can't perfectly reconstruct the original action_type from
        # the prompt status alone, but we can detect when the policy
        # would take a fundamentally different path
        if prompt.status in ("resolved", "reply_received") and decision.action_type == "deny":
            report.diffs.append(
                DecisionDiff(
                    prompt_id=prompt.prompt_id,
                    prompt_type=prompt.prompt_type,
                    field="action_type",
                    original="resolved",
                    replayed="deny",
                )
            )
