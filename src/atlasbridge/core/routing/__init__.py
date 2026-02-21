"""Routing subsystem — prompt routing and intent classification."""

from atlasbridge.core.routing.intent import (
    ClassificationResult,
    IntentRouter,
    PolicyRouteClassifier,
    RouteClassifier,
    RouteIntent,
)
from atlasbridge.core.routing.router import PromptRouter

__all__ = [
    "ClassificationResult",
    "IntentRouter",
    "PolicyRouteClassifier",
    "PromptRouter",
    "RouteClassifier",
    "RouteIntent",
]
