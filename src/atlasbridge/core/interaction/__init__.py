"""Interaction subsystem — classification, planning, execution, and chat mode."""

from atlasbridge.core.interaction.classifier import InteractionClass, InteractionClassifier
from atlasbridge.core.interaction.engine import InteractionEngine
from atlasbridge.core.interaction.executor import InjectionResult, InteractionExecutor
from atlasbridge.core.interaction.ml_classifier import (
    MLClassification,
    MLClassifier,
    NullMLClassifier,
)
from atlasbridge.core.interaction.output_forwarder import OutputForwarder
from atlasbridge.core.interaction.output_router import OutputKind, OutputRouter
from atlasbridge.core.interaction.plan import InteractionPlan, build_plan

__all__ = [
    "InjectionResult",
    "InteractionClass",
    "InteractionClassifier",
    "InteractionEngine",
    "InteractionExecutor",
    "InteractionPlan",
    "MLClassification",
    "MLClassifier",
    "NullMLClassifier",
    "OutputForwarder",
    "OutputKind",
    "OutputRouter",
    "build_plan",
]
