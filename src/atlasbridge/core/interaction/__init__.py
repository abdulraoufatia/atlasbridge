"""Interaction subsystem — classification, planning, execution, and chat mode."""

from atlasbridge.core.interaction.classifier import InteractionClass, InteractionClassifier
from atlasbridge.core.interaction.executor import InjectionResult, InteractionExecutor
from atlasbridge.core.interaction.plan import InteractionPlan, build_plan

__all__ = [
    "InjectionResult",
    "InteractionClass",
    "InteractionClassifier",
    "InteractionExecutor",
    "InteractionPlan",
    "build_plan",
]
