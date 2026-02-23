"""Unit tests for plan detection in agent output."""

from __future__ import annotations

from atlasbridge.core.interaction.plan_detector import DetectedPlan, detect_plan


class TestPlanWithHeader:
    def test_detect_plan_header_with_steps(self) -> None:
        text = """Plan:
1. Create the database schema
2. Add the migration script
3. Run the tests
"""
        plan = detect_plan(text)
        assert plan is not None
        assert len(plan.steps) == 3
        assert plan.steps[0] == "Create the database schema"

    def test_detect_markdown_plan_header(self) -> None:
        text = """## Plan

1. Update the config file
2. Add validation logic
"""
        plan = detect_plan(text)
        assert plan is not None
        assert len(plan.steps) == 2

    def test_detect_conversational_plan_header(self) -> None:
        text = """Here's my plan:

1. Install the dependency
2. Configure the module
3. Write tests
"""
        plan = detect_plan(text)
        assert plan is not None
        assert len(plan.steps) == 3

    def test_detect_h3_plan_header(self) -> None:
        text = """### Plan

1. Fix the bug
2. Add a regression test
"""
        plan = detect_plan(text)
        assert plan is not None
        assert len(plan.steps) == 2


class TestHeaderlessPlan:
    def test_detect_headerless_steps_with_verbs(self) -> None:
        text = """1. Create the new module
2. Add the API endpoint
3. Write integration tests
4. Update the documentation
"""
        plan = detect_plan(text)
        assert plan is not None
        assert len(plan.steps) == 4

    def test_reject_too_few_steps(self) -> None:
        text = """1. Fix the bug
2. Test it
"""
        # Only 2 steps without a header → should be rejected
        plan = detect_plan(text)
        assert plan is None

    def test_reject_non_consecutive_numbering(self) -> None:
        text = """1. First thing
3. Third thing
5. Fifth thing
"""
        plan = detect_plan(text)
        assert plan is None

    def test_reject_numbered_output_without_verbs(self) -> None:
        text = """1. foo.txt
2. bar.txt
3. baz.txt
4. qux.txt
"""
        plan = detect_plan(text)
        assert plan is None


class TestStepExtraction:
    def test_steps_extracted_correctly(self) -> None:
        text = """Plan:
1. Create the migration file
2. Update the model definition
3. Run pytest to verify
"""
        plan = detect_plan(text)
        assert plan is not None
        assert plan.steps[0] == "Create the migration file"
        assert plan.steps[1] == "Update the model definition"
        assert plan.steps[2] == "Run pytest to verify"

    def test_start_end_offsets(self) -> None:
        prefix = "Some preamble text.\n\n"
        plan_text = """Plan:
1. Add the feature
2. Test the feature
"""
        text = prefix + plan_text
        plan = detect_plan(text)
        assert plan is not None
        assert plan.start_offset >= len(prefix) - 1
        assert plan.end_offset > plan.start_offset

    def test_title_from_header(self) -> None:
        text = """## Plan

1. Step one
2. Step two
"""
        plan = detect_plan(text)
        assert plan is not None
        assert "Plan" in plan.title


class TestEdgeCases:
    def test_no_plan_in_normal_text(self) -> None:
        text = "This is just regular output from the CLI tool."
        assert detect_plan(text) is None

    def test_no_plan_in_empty_text(self) -> None:
        assert detect_plan("") is None

    def test_plan_with_parenthesized_numbers(self) -> None:
        text = """Plan:
1) Create the schema
2) Run migrations
3) Verify data
"""
        plan = detect_plan(text)
        assert plan is not None
        assert len(plan.steps) == 3

    def test_frozen_dataclass(self) -> None:
        plan = DetectedPlan(
            title="Test",
            steps=["Step 1"],
            raw_text="raw",
            start_offset=0,
            end_offset=10,
        )
        assert plan.title == "Test"
