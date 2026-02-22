"""
Safety tests: ML classifier invariants.

Verifies that:
  1. ML output never triggers execution without deterministic HIGH confirmation.
  2. NullMLClassifier produces identical behavior to no-fuser path.
  3. Fusion disagreement always sets disagreement=True.
  4. ML is optional (engine works without fuser).
  5. FOLDER_TRUST plan has escalate_on_exhaustion=True.
  6. RAW_TERMINAL plan always escalates.
"""

from __future__ import annotations

from atlasbridge.core.interaction.classifier import InteractionClass, InteractionClassifier
from atlasbridge.core.interaction.fuser import ClassificationFuser
from atlasbridge.core.interaction.ml_classifier import (
    MLClassification,
    NullMLClassifier,
)
from atlasbridge.core.interaction.plan import build_plan
from atlasbridge.core.prompt.models import Confidence, PromptEvent, PromptType


def _event(
    prompt_type: PromptType = PromptType.TYPE_YES_NO,
    confidence: Confidence = Confidence.HIGH,
    excerpt: str = "Continue? [y/N]",
) -> PromptEvent:
    return PromptEvent.create(
        session_id="sess-001",
        prompt_type=prompt_type,
        confidence=confidence,
        excerpt=excerpt,
    )


class _AggressiveML:
    """ML classifier that always disagrees with the deterministic classifier."""

    def classify(self, text: str, prompt_type: str) -> MLClassification | None:
        # Always say it's a password input, regardless
        return MLClassification.PASSWORD_INPUT


class TestMLNeverOverridesHighDeterministic:
    def test_aggressive_ml_cannot_override_high(self) -> None:
        """Even an aggressive ML classifier cannot change a HIGH deterministic result."""
        fuser = ClassificationFuser(InteractionClassifier(), _AggressiveML())
        for pt in PromptType:
            event = _event(prompt_type=pt, confidence=Confidence.HIGH)
            result = fuser.fuse(event)
            # At HIGH confidence, deterministic always wins
            det = InteractionClassifier().classify(event)
            assert result.interaction_class == det
            assert result.source == "deterministic"


class TestNullMLIdenticalToRawClassifier:
    def test_all_types_and_confidences(self) -> None:
        """NullMLClassifier produces identical results to using classifier directly."""
        det = InteractionClassifier()
        fuser = ClassificationFuser(det, NullMLClassifier())

        for pt in PromptType:
            for conf in Confidence:
                event = _event(prompt_type=pt, confidence=conf)
                fused = fuser.fuse(event)
                raw = det.classify(event)
                assert fused.interaction_class == raw, (
                    f"Mismatch for {pt}/{conf}: fused={fused.interaction_class}, raw={raw}"
                )


class TestFusionDisagreementAlwaysFlags:
    def test_med_disagreement_flags(self) -> None:
        """Any disagreement at MED confidence sets disagreement=True."""
        fuser = ClassificationFuser(InteractionClassifier(), _AggressiveML())
        # YES_NO at MED + ML says PASSWORD → disagreement
        event = _event(confidence=Confidence.MED)
        result = fuser.fuse(event)
        assert result.disagreement is True


class TestMLIsOptional:
    def test_fuser_works_without_ml(self) -> None:
        """ClassificationFuser works with ml=None (uses NullMLClassifier)."""
        fuser = ClassificationFuser(InteractionClassifier(), ml=None)
        event = _event(confidence=Confidence.HIGH)
        result = fuser.fuse(event)
        assert result.interaction_class == InteractionClass.YES_NO
        assert result.source == "deterministic"


class TestFolderTrustPlanEscalates:
    def test_escalate_on_exhaustion(self) -> None:
        plan = build_plan(InteractionClass.FOLDER_TRUST)
        assert plan.escalate_on_exhaustion is True


class TestRawTerminalAlwaysEscalates:
    def test_escalate_on_exhaustion(self) -> None:
        plan = build_plan(InteractionClass.RAW_TERMINAL)
        assert plan.escalate_on_exhaustion is True

    def test_no_injection(self) -> None:
        """RAW_TERMINAL never injects (append_cr=False, no retries)."""
        plan = build_plan(InteractionClass.RAW_TERMINAL)
        assert plan.append_cr is False
        assert plan.max_retries == 0
        assert plan.verify_advance is False
