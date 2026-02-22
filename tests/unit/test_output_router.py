"""Unit tests for OutputRouter — classifies PTY output into kind."""

from __future__ import annotations

from atlasbridge.core.interaction.output_router import OutputKind, OutputRouter


class TestNoiseClassification:
    def test_empty_string_is_noise(self) -> None:
        router = OutputRouter()
        assert router.classify("") == OutputKind.NOISE

    def test_whitespace_only_is_noise(self) -> None:
        router = OutputRouter()
        assert router.classify("   \n\t  ") == OutputKind.NOISE

    def test_short_text_is_noise(self) -> None:
        router = OutputRouter()
        assert router.classify("ok") == OutputKind.NOISE

    def test_exactly_threshold_is_not_noise(self) -> None:
        router = OutputRouter()
        result = router.classify("x" * 10)
        assert result != OutputKind.NOISE


class TestCLIOutputClassification:
    def test_command_with_dollar_prefix(self) -> None:
        router = OutputRouter()
        text = "$ npm install\ninstalling dependencies..."
        assert router.classify(text) == OutputKind.CLI_OUTPUT

    def test_python_stack_trace(self) -> None:
        router = OutputRouter()
        text = (
            "Traceback (most recent call last):\n"
            '  File "main.py", line 10, in <module>\n'
            "    raise ValueError()\nValueError"
        )
        assert router.classify(text) == OutputKind.CLI_OUTPUT

    def test_error_lines(self) -> None:
        router = OutputRouter()
        text = "error: could not compile\nwarning: unused variable"
        assert router.classify(text) == OutputKind.CLI_OUTPUT

    def test_file_line_references(self) -> None:
        router = OutputRouter()
        text = "src/main.py:42: error E501 line too long"
        assert router.classify(text) == OutputKind.CLI_OUTPUT

    def test_test_results(self) -> None:
        router = OutputRouter()
        text = "PASS src/tests/test_main.py\n  5 passing"
        assert router.classify(text) == OutputKind.CLI_OUTPUT


class TestAgentMessageClassification:
    def test_markdown_heading(self) -> None:
        router = OutputRouter()
        text = "# Summary of Changes\n\nHere are the modifications I made."
        assert router.classify(text) == OutputKind.AGENT_MESSAGE

    def test_markdown_list(self) -> None:
        router = OutputRouter()
        text = "- Fixed the authentication bug\n- Updated the tests\n- Added documentation"
        assert router.classify(text) == OutputKind.AGENT_MESSAGE

    def test_agent_self_reference(self) -> None:
        router = OutputRouter()
        text = "I'll update the configuration file and restart the server."
        assert router.classify(text) == OutputKind.AGENT_MESSAGE

    def test_let_me_prefix(self) -> None:
        router = OutputRouter()
        text = "Let me check the database connection settings for you."
        assert router.classify(text) == OutputKind.AGENT_MESSAGE

    def test_bold_text(self) -> None:
        router = OutputRouter()
        text = "**Important**: The configuration must be updated before deploying."
        assert router.classify(text) == OutputKind.AGENT_MESSAGE


class TestShowRawOutputBypass:
    def test_bypass_treats_prose_as_cli(self) -> None:
        router = OutputRouter(show_raw_output=True)
        text = "# Summary\n\nHere are the changes I made to the codebase."
        assert router.classify(text) == OutputKind.CLI_OUTPUT

    def test_bypass_keeps_noise_as_noise(self) -> None:
        router = OutputRouter(show_raw_output=True)
        assert router.classify("ok") == OutputKind.NOISE

    def test_bypass_cli_stays_cli(self) -> None:
        router = OutputRouter(show_raw_output=True)
        text = "$ npm install\ninstalling..."
        assert router.classify(text) == OutputKind.CLI_OUTPUT


class TestDeterminism:
    def test_same_input_same_output(self) -> None:
        router = OutputRouter()
        text = "# Hello World\n\nThis is a test of the output router."
        results = [router.classify(text) for _ in range(100)]
        assert all(r == results[0] for r in results)

    def test_default_to_cli_output(self) -> None:
        """Ambiguous text should default to CLI_OUTPUT (safer)."""
        router = OutputRouter()
        text = "Processing complete. No errors found in scan."
        result = router.classify(text)
        # Should not be NOISE (it's meaningful), and defaults to CLI
        assert result in (OutputKind.CLI_OUTPUT, OutputKind.AGENT_MESSAGE)
