"""
ClassificationFuser — fuses deterministic and ML classifications.

Fusion rules ensure safety: the deterministic classifier always wins
when it has HIGH confidence.  ML can refine MED/LOW classifications
and introduce ML-only types (FOLDER_TRUST, RAW_TERMINAL).  Any
material disagreement at MED confidence triggers escalation.

Invariant: ML output NEVER triggers execution without deterministic
confirmation at HIGH confidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from atlasbridge.core.interaction.classifier import InteractionClass, InteractionClassifier
from atlasbridge.core.interaction.ml_classifier import (
    MLClassification,
    NullMLClassifier,
)

if TYPE_CHECKING:
    from atlasbridge.core.interaction.ml_classifier import MLClassifier
    from atlasbridge.core.prompt.models import PromptEvent

logger = structlog.get_logger()


# Map MLClassification → InteractionClass where names match
_ML_TO_IC: dict[MLClassification, InteractionClass] = {
    MLClassification.YES_NO: InteractionClass.YES_NO,
    MLClassification.CONFIRM_ENTER: InteractionClass.CONFIRM_ENTER,
    MLClassification.NUMBERED_CHOICE: InteractionClass.NUMBERED_CHOICE,
    MLClassification.FREE_TEXT: InteractionClass.FREE_TEXT,
    MLClassification.PASSWORD_INPUT: InteractionClass.PASSWORD_INPUT,
    MLClassification.CHAT_INPUT: InteractionClass.CHAT_INPUT,
    MLClassification.FOLDER_TRUST: InteractionClass.FOLDER_TRUST,
    MLClassification.RAW_TERMINAL: InteractionClass.RAW_TERMINAL,
}

# ML-only types that the deterministic classifier cannot produce
_ML_ONLY_TYPES = frozenset({MLClassification.FOLDER_TRUST, MLClassification.RAW_TERMINAL})


@dataclass(frozen=True)
class FusedClassification:
    """Result of deterministic + ML fusion."""

    interaction_class: InteractionClass
    source: str  # "deterministic" | "ml" | "fused"
    confidence: str  # "high" | "medium" | "low"
    disagreement: bool = False  # True if deterministic and ML disagreed


class ClassificationFuser:
    """Fuses deterministic and optional ML classifications.

    Fusion rules (deterministic wins when confident):
      1. Deterministic HIGH → use deterministic, ignore ML.
      2. ML returns None → use deterministic at any confidence.
      3. Deterministic MED + ML agrees → use deterministic (boosted).
      4. Deterministic MED + ML disagrees → escalate (disagreement=True).
      5. Deterministic LOW + ML has opinion → use ML.
      6. ML returns FOLDER_TRUST or RAW_TERMINAL → use ML
         (these have no deterministic equivalent).

    Invariant: ML never triggers execution without deterministic
    confirmation at HIGH confidence.
    """

    def __init__(
        self,
        deterministic: InteractionClassifier,
        ml: MLClassifier | None = None,
    ) -> None:
        self._det = deterministic
        self._ml: MLClassifier = ml or NullMLClassifier()

    def fuse(self, event: PromptEvent | None) -> FusedClassification:
        """Run both classifiers and apply fusion rules."""
        det_ic = self._det.classify(event)
        det_confidence = _event_confidence(event)

        # No event → chat input; ML irrelevant
        if event is None:
            return FusedClassification(
                interaction_class=det_ic,
                source="deterministic",
                confidence="high",
            )

        ml_result = self._ml.classify(event.excerpt, event.prompt_type)

        # Rule 2: ML has no opinion → deterministic wins
        if ml_result is None or ml_result == MLClassification.UNKNOWN:
            return FusedClassification(
                interaction_class=det_ic,
                source="deterministic",
                confidence=det_confidence,
            )

        ml_ic = _ML_TO_IC.get(ml_result)

        # Rule 6: ML-only types (FOLDER_TRUST, RAW_TERMINAL) — use ML
        if ml_result in _ML_ONLY_TYPES and ml_ic is not None:
            logger.debug(
                "fuser_ml_only_type",
                ml_type=ml_result,
                det_type=det_ic,
            )
            return FusedClassification(
                interaction_class=ml_ic,
                source="ml",
                confidence="medium",
            )

        # Rule 1: Deterministic HIGH → always wins
        if det_confidence == "high":
            return FusedClassification(
                interaction_class=det_ic,
                source="deterministic",
                confidence="high",
            )

        # Rule 3 & 4: Deterministic MED
        if det_confidence == "medium":
            if ml_ic == det_ic:
                # Rule 3: agreement → boost
                return FusedClassification(
                    interaction_class=det_ic,
                    source="fused",
                    confidence="high",
                )
            else:
                # Rule 4: disagreement → escalate
                logger.warning(
                    "fuser_disagreement",
                    det_type=det_ic,
                    ml_type=ml_result,
                    confidence=det_confidence,
                )
                return FusedClassification(
                    interaction_class=det_ic,
                    source="deterministic",
                    confidence="low",
                    disagreement=True,
                )

        # Rule 5: Deterministic LOW + ML has opinion → use ML
        if ml_ic is not None:
            return FusedClassification(
                interaction_class=ml_ic,
                source="ml",
                confidence="medium",
            )

        # Fallback: use deterministic
        return FusedClassification(
            interaction_class=det_ic,
            source="deterministic",
            confidence=det_confidence,
        )


def _event_confidence(event: PromptEvent | None) -> str:
    """Extract confidence string from a PromptEvent."""
    if event is None:
        return "high"
    # PromptEvent.confidence is a Confidence StrEnum ("high", "medium", "low")
    return str(event.confidence)
