"""Unit tests for MLClassifier protocol and NullMLClassifier."""

from __future__ import annotations

from atlasbridge.core.interaction.ml_classifier import (
    MLClassification,
    MLClassifier,
    NullMLClassifier,
)


class TestNullMLClassifier:
    def test_always_returns_none(self) -> None:
        clf = NullMLClassifier()
        assert clf.classify("Continue? [y/N]", "yes_no") is None
        assert clf.classify("Enter password:", "free_text") is None
        assert clf.classify("", "") is None

    def test_is_deterministic(self) -> None:
        clf = NullMLClassifier()
        results = [clf.classify("test prompt", "free_text") for _ in range(100)]
        assert all(r is None for r in results)

    def test_satisfies_protocol(self) -> None:
        clf = NullMLClassifier()
        assert isinstance(clf, MLClassifier)


class TestMLClassification:
    def test_all_values_exist(self) -> None:
        expected = {
            "yes_no",
            "confirm_enter",
            "numbered_choice",
            "free_text",
            "password_input",
            "chat_input",
            "folder_trust",
            "raw_terminal",
            "unknown",
        }
        actual = {v.value for v in MLClassification}
        assert actual == expected

    def test_count(self) -> None:
        assert len(MLClassification) == 9

    def test_ml_only_types_exist(self) -> None:
        """FOLDER_TRUST and RAW_TERMINAL are ML-only classifications."""
        assert MLClassification.FOLDER_TRUST == "folder_trust"
        assert MLClassification.RAW_TERMINAL == "raw_terminal"
        assert MLClassification.UNKNOWN == "unknown"
