"""Unit tests for InteractionClassifier."""

from __future__ import annotations

import pytest

from atlasbridge.core.interaction.classifier import InteractionClass, InteractionClassifier
from atlasbridge.core.prompt.models import Confidence, PromptEvent, PromptType


@pytest.fixture
def classifier() -> InteractionClassifier:
    return InteractionClassifier()


def _event(
    prompt_type: PromptType = PromptType.TYPE_FREE_TEXT,
    excerpt: str = "some prompt text",
    confidence: Confidence = Confidence.HIGH,
) -> PromptEvent:
    return PromptEvent.create(
        session_id="test-session-abc123",
        prompt_type=prompt_type,
        confidence=confidence,
        excerpt=excerpt,
    )


# ---------------------------------------------------------------------------
# YES_NO classification
# ---------------------------------------------------------------------------


class TestYesNoClassification:
    def test_yes_no_event(self, classifier: InteractionClassifier) -> None:
        event = _event(prompt_type=PromptType.TYPE_YES_NO, excerpt="Overwrite? [y/N]")
        assert classifier.classify(event) == InteractionClass.YES_NO

    def test_yes_no_with_action_verb(self, classifier: InteractionClassifier) -> None:
        event = _event(prompt_type=PromptType.TYPE_YES_NO, excerpt="Delete file? (Yes/No)")
        assert classifier.classify(event) == InteractionClass.YES_NO


# ---------------------------------------------------------------------------
# CONFIRM_ENTER classification
# ---------------------------------------------------------------------------


class TestConfirmEnterClassification:
    def test_confirm_enter_event(self, classifier: InteractionClassifier) -> None:
        event = _event(
            prompt_type=PromptType.TYPE_CONFIRM_ENTER,
            excerpt="Press Enter to continue",
        )
        assert classifier.classify(event) == InteractionClass.CONFIRM_ENTER

    def test_more_prompt(self, classifier: InteractionClassifier) -> None:
        event = _event(
            prompt_type=PromptType.TYPE_CONFIRM_ENTER,
            excerpt="--More--",
        )
        assert classifier.classify(event) == InteractionClass.CONFIRM_ENTER


# ---------------------------------------------------------------------------
# NUMBERED_CHOICE classification
# ---------------------------------------------------------------------------


class TestNumberedChoiceClassification:
    def test_multiple_choice_event(self, classifier: InteractionClassifier) -> None:
        event = _event(
            prompt_type=PromptType.TYPE_MULTIPLE_CHOICE,
            excerpt="1) Fast\n2) Balanced\n3) Thorough",
        )
        assert classifier.classify(event) == InteractionClass.NUMBERED_CHOICE

    def test_lettered_choices(self, classifier: InteractionClassifier) -> None:
        event = _event(
            prompt_type=PromptType.TYPE_MULTIPLE_CHOICE,
            excerpt="[A] Option one [B] Option two",
        )
        assert classifier.classify(event) == InteractionClass.NUMBERED_CHOICE


# ---------------------------------------------------------------------------
# FREE_TEXT classification
# ---------------------------------------------------------------------------


class TestFreeTextClassification:
    def test_plain_free_text(self, classifier: InteractionClassifier) -> None:
        event = _event(
            prompt_type=PromptType.TYPE_FREE_TEXT,
            excerpt="Enter your name:",
        )
        assert classifier.classify(event) == InteractionClass.FREE_TEXT

    def test_email_prompt(self, classifier: InteractionClassifier) -> None:
        event = _event(
            prompt_type=PromptType.TYPE_FREE_TEXT,
            excerpt="Email address:",
        )
        assert classifier.classify(event) == InteractionClass.FREE_TEXT

    def test_branch_name_prompt(self, classifier: InteractionClassifier) -> None:
        event = _event(
            prompt_type=PromptType.TYPE_FREE_TEXT,
            excerpt="Branch name:",
        )
        assert classifier.classify(event) == InteractionClass.FREE_TEXT


# ---------------------------------------------------------------------------
# PASSWORD_INPUT classification
# ---------------------------------------------------------------------------


class TestPasswordClassification:
    def test_password_prompt(self, classifier: InteractionClassifier) -> None:
        event = _event(
            prompt_type=PromptType.TYPE_FREE_TEXT,
            excerpt="Password:",
        )
        assert classifier.classify(event) == InteractionClass.PASSWORD_INPUT

    def test_token_prompt(self, classifier: InteractionClassifier) -> None:
        event = _event(
            prompt_type=PromptType.TYPE_FREE_TEXT,
            excerpt="Enter your API token:",
        )
        assert classifier.classify(event) == InteractionClass.PASSWORD_INPUT

    def test_api_key_prompt(self, classifier: InteractionClassifier) -> None:
        event = _event(
            prompt_type=PromptType.TYPE_FREE_TEXT,
            excerpt="API key:",
        )
        assert classifier.classify(event) == InteractionClass.PASSWORD_INPUT

    def test_secret_prompt(self, classifier: InteractionClassifier) -> None:
        event = _event(
            prompt_type=PromptType.TYPE_FREE_TEXT,
            excerpt="Secret:",
        )
        assert classifier.classify(event) == InteractionClass.PASSWORD_INPUT

    def test_passphrase_prompt(self, classifier: InteractionClassifier) -> None:
        event = _event(
            prompt_type=PromptType.TYPE_FREE_TEXT,
            excerpt="SSH key passphrase:",
        )
        assert classifier.classify(event) == InteractionClass.PASSWORD_INPUT

    def test_gpg_password_prompt(self, classifier: InteractionClassifier) -> None:
        event = _event(
            prompt_type=PromptType.TYPE_FREE_TEXT,
            excerpt="GPG key passphrase:",
        )
        assert classifier.classify(event) == InteractionClass.PASSWORD_INPUT

    def test_credential_prompt(self, classifier: InteractionClassifier) -> None:
        event = _event(
            prompt_type=PromptType.TYPE_FREE_TEXT,
            excerpt="Credential:",
        )
        assert classifier.classify(event) == InteractionClass.PASSWORD_INPUT


# ---------------------------------------------------------------------------
# CHAT_INPUT classification
# ---------------------------------------------------------------------------


class TestChatInputClassification:
    def test_none_event_is_chat_input(self, classifier: InteractionClassifier) -> None:
        assert classifier.classify(None) == InteractionClass.CHAT_INPUT


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_input_same_output(self, classifier: InteractionClassifier) -> None:
        event = _event(
            prompt_type=PromptType.TYPE_FREE_TEXT,
            excerpt="Password:",
        )
        results = [classifier.classify(event) for _ in range(10)]
        assert all(r == InteractionClass.PASSWORD_INPUT for r in results)

    def test_classifier_is_stateless(self) -> None:
        c1 = InteractionClassifier()
        c2 = InteractionClassifier()
        event = _event(prompt_type=PromptType.TYPE_YES_NO, excerpt="Continue? [y/n]")
        assert c1.classify(event) == c2.classify(event)
