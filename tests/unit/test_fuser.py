"""Unit tests for ClassificationFuser — deterministic + ML fusion rules."""

from __future__ import annotations

from atlasbridge.core.interaction.classifier import InteractionClass, InteractionClassifier
from atlasbridge.core.interaction.fuser import ClassificationFuser
from atlasbridge.core.interaction.ml_classifier import (
    MLClassification,
    NullMLClassifier,
)
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


class _StubMLClassifier:
    """ML classifier that returns a fixed result."""

    def __init__(self, result: MLClassification | None) -> None:
        self._result = result

    def classify(self, text: str, prompt_type: str) -> MLClassification | None:
        return self._result


class TestRule1DeterministicHighWins:
    def test_ignores_ml_when_det_high(self) -> None:
        ml = _StubMLClassifier(MLClassification.NUMBERED_CHOICE)
        fuser = ClassificationFuser(InteractionClassifier(), ml)
        event = _event(confidence=Confidence.HIGH)
        result = fuser.fuse(event)
        assert result.interaction_class == InteractionClass.YES_NO
        assert result.source == "deterministic"
        assert result.confidence == "high"
        assert result.disagreement is False

    def test_high_det_overrides_ml_password(self) -> None:
        ml = _StubMLClassifier(MLClassification.PASSWORD_INPUT)
        fuser = ClassificationFuser(InteractionClassifier(), ml)
        event = _event(confidence=Confidence.HIGH)
        result = fuser.fuse(event)
        assert result.interaction_class == InteractionClass.YES_NO


class TestRule2MLNoneUsesDet:
    def test_null_ml_uses_deterministic(self) -> None:
        fuser = ClassificationFuser(InteractionClassifier(), NullMLClassifier())
        event = _event(confidence=Confidence.MED)
        result = fuser.fuse(event)
        assert result.interaction_class == InteractionClass.YES_NO
        assert result.source == "deterministic"

    def test_ml_unknown_uses_deterministic(self) -> None:
        ml = _StubMLClassifier(MLClassification.UNKNOWN)
        fuser = ClassificationFuser(InteractionClassifier(), ml)
        event = _event(confidence=Confidence.MED)
        result = fuser.fuse(event)
        assert result.interaction_class == InteractionClass.YES_NO
        assert result.source == "deterministic"


class TestRule3MedAgreement:
    def test_med_agreement_boosts_to_fused(self) -> None:
        ml = _StubMLClassifier(MLClassification.YES_NO)
        fuser = ClassificationFuser(InteractionClassifier(), ml)
        event = _event(confidence=Confidence.MED)
        result = fuser.fuse(event)
        assert result.interaction_class == InteractionClass.YES_NO
        assert result.source == "fused"
        assert result.confidence == "high"
        assert result.disagreement is False


class TestRule4MedDisagreement:
    def test_med_disagreement_escalates(self) -> None:
        ml = _StubMLClassifier(MLClassification.FREE_TEXT)
        fuser = ClassificationFuser(InteractionClassifier(), ml)
        event = _event(confidence=Confidence.MED)
        result = fuser.fuse(event)
        assert result.disagreement is True
        assert result.confidence == "low"
        assert result.source == "deterministic"


class TestRule5LowUsesML:
    def test_low_det_uses_ml(self) -> None:
        ml = _StubMLClassifier(MLClassification.CONFIRM_ENTER)
        fuser = ClassificationFuser(InteractionClassifier(), ml)
        event = _event(confidence=Confidence.LOW)
        result = fuser.fuse(event)
        assert result.interaction_class == InteractionClass.CONFIRM_ENTER
        assert result.source == "ml"
        assert result.confidence == "medium"


class TestRule6MLOnlyTypes:
    def test_folder_trust_from_ml(self) -> None:
        ml = _StubMLClassifier(MLClassification.FOLDER_TRUST)
        fuser = ClassificationFuser(InteractionClassifier(), ml)
        event = _event(
            prompt_type=PromptType.TYPE_YES_NO,
            confidence=Confidence.HIGH,
            excerpt="Trust this folder? [y/N]",
        )
        result = fuser.fuse(event)
        assert result.interaction_class == InteractionClass.FOLDER_TRUST
        assert result.source == "ml"

    def test_raw_terminal_from_ml(self) -> None:
        ml = _StubMLClassifier(MLClassification.RAW_TERMINAL)
        fuser = ClassificationFuser(InteractionClassifier(), ml)
        event = _event(
            prompt_type=PromptType.TYPE_FREE_TEXT,
            confidence=Confidence.MED,
            excerpt="Use arrow keys to select:",
        )
        result = fuser.fuse(event)
        assert result.interaction_class == InteractionClass.RAW_TERMINAL
        assert result.source == "ml"


class TestChatInput:
    def test_none_event_returns_chat_input(self) -> None:
        fuser = ClassificationFuser(InteractionClassifier(), NullMLClassifier())
        result = fuser.fuse(None)
        assert result.interaction_class == InteractionClass.CHAT_INPUT
        assert result.source == "deterministic"
        assert result.confidence == "high"


class TestNullMLIdenticalToNoFuser:
    def test_null_ml_matches_raw_classifier(self) -> None:
        """NullMLClassifier produces same results as using classifier directly."""
        det = InteractionClassifier()
        fuser = ClassificationFuser(det, NullMLClassifier())

        for pt in PromptType:
            for conf in Confidence:
                event = _event(prompt_type=pt, confidence=conf)
                fused = fuser.fuse(event)
                raw = det.classify(event)
                assert fused.interaction_class == raw


class TestDeterminism:
    def test_same_input_same_output(self) -> None:
        ml = _StubMLClassifier(MLClassification.FREE_TEXT)
        fuser = ClassificationFuser(InteractionClassifier(), ml)
        event = _event(confidence=Confidence.MED)
        results = [fuser.fuse(event) for _ in range(100)]
        first = results[0]
        assert all(r.interaction_class == first.interaction_class for r in results)
        assert all(r.source == first.source for r in results)
        assert all(r.disagreement == first.disagreement for r in results)
