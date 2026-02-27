"""Unit tests for Expert Agent governed tools."""

from __future__ import annotations

from atlasbridge.core.agent.tools import get_agent_registry


class TestAgentToolDefinitions:
    """All agent tools have valid definitions."""

    def setup_method(self) -> None:
        self.registry = get_agent_registry()
        self.tools = self.registry.list_all()

    def test_registry_has_tools(self) -> None:
        assert len(self.tools) >= 10, f"Expected at least 10 tools, got {len(self.tools)}"

    def test_all_tools_have_names(self) -> None:
        for tool in self.tools:
            assert tool.name, f"Tool missing name: {tool}"
            assert tool.name.startswith("ab_"), f"Tool name must start with ab_: {tool.name}"

    def test_all_tools_have_descriptions(self) -> None:
        for tool in self.tools:
            assert tool.description, f"Tool {tool.name} missing description"

    def test_all_tools_have_valid_json_schema(self) -> None:
        for tool in self.tools:
            schema = tool.parameters
            assert isinstance(schema, dict), f"Tool {tool.name} parameters not a dict"
            assert schema.get("type") == "object", f"Tool {tool.name} schema type must be object"
            if "properties" in schema:
                assert isinstance(schema["properties"], dict)

    def test_safe_tools_exist(self) -> None:
        safe_names = {
            "ab_list_sessions",
            "ab_get_session",
            "ab_list_prompts",
            "ab_get_audit_events",
            "ab_get_traces",
            "ab_check_integrity",
            "ab_get_config",
            "ab_get_policy",
            "ab_explain_decision",
            "ab_get_stats",
        }
        tool_names = {t.name for t in self.tools}
        for name in safe_names:
            assert name in tool_names, f"Missing safe tool: {name}"

    def test_moderate_tools_exist(self) -> None:
        moderate_names = {"ab_validate_policy", "ab_test_policy"}
        tool_names = {t.name for t in self.tools}
        for name in moderate_names:
            assert name in tool_names, f"Missing moderate tool: {name}"

    def test_dangerous_tools_exist(self) -> None:
        dangerous_names = {"ab_set_mode", "ab_kill_switch"}
        tool_names = {t.name for t in self.tools}
        for name in dangerous_names:
            assert name in tool_names, f"Missing dangerous tool: {name}"

    def test_risk_levels_correct(self) -> None:
        safe = {
            "ab_list_sessions",
            "ab_get_session",
            "ab_list_prompts",
            "ab_get_audit_events",
            "ab_get_traces",
            "ab_check_integrity",
            "ab_get_config",
            "ab_get_policy",
            "ab_explain_decision",
            "ab_get_stats",
        }
        moderate = {"ab_validate_policy", "ab_test_policy"}
        dangerous = {"ab_set_mode", "ab_kill_switch"}

        for tool in self.tools:
            if tool.name in safe:
                assert tool.risk_level == "safe", (
                    f"{tool.name} should be safe, got {tool.risk_level}"
                )
            elif tool.name in moderate:
                assert tool.risk_level == "moderate", (
                    f"{tool.name} should be moderate, got {tool.risk_level}"
                )
            elif tool.name in dangerous:
                assert tool.risk_level == "dangerous", (
                    f"{tool.name} should be dangerous, got {tool.risk_level}"
                )

    def test_tool_lookup_by_name(self) -> None:
        tool = self.registry.get("ab_list_sessions")
        assert tool is not None
        assert tool.name == "ab_list_sessions"

    def test_unknown_tool_returns_none(self) -> None:
        tool = self.registry.get("nonexistent_tool")
        assert tool is None
