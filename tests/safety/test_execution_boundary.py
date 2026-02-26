"""Safety tests: local-only execution boundary enforcement.

Verifies that all execution paths flow through the guarded pipeline
(gate evaluation + adapter injection) and that no bypass paths exist.

Part of Epic #145 — Local-Only Execution Boundary.
Closes #146, #147, #148, #149, #150.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SRC_ROOT = Path(__file__).parents[2] / "src" / "atlasbridge"

# Modules that MUST NOT contain direct subprocess/os.system/exec calls
# (channels and cloud should never execute anything)
NO_EXEC_MODULES = [
    SRC_ROOT / "channels",
    SRC_ROOT / "cloud",
    SRC_ROOT / "dashboard",
]

# The ONLY modules allowed to call tty.inject_reply or write to PTY
ALLOWED_INJECTION_MODULES = {
    "adapters/claude_code.py",
    "adapters/openai_cli.py",
    "adapters/gemini_cli.py",
    "core/interaction/executor.py",
    "core/routing/router.py",
    "os/tty/base.py",
    "os/tty/macos.py",
    "os/tty/linux.py",
}

# Dangerous exec-like calls that should never appear in channel/cloud code
DANGEROUS_CALLS = {"subprocess.run", "subprocess.Popen", "subprocess.call", "os.system", "exec"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collect_python_files(directory: Path) -> list[Path]:
    """Recursively collect all .py files under a directory."""
    if not directory.exists():
        return []
    return sorted(directory.rglob("*.py"))


def _get_call_names(node: ast.AST) -> list[str]:
    """Extract dotted call names from an AST Call node."""
    names: list[str] = []
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            names.append(f"{func.value.id}.{func.attr}")
        elif isinstance(func, ast.Name):
            names.append(func.id)
    return names


# ---------------------------------------------------------------------------
# #146: No direct execution entrypoints in channel/cloud/dashboard code
# ---------------------------------------------------------------------------


class TestNoDirectExecution:
    """Channels, cloud, and dashboard modules must never execute commands."""

    @pytest.mark.safety
    def test_no_subprocess_in_restricted_modules(self) -> None:
        """No subprocess/exec calls in channel, cloud, or dashboard code."""
        violations: list[str] = []
        for module_dir in NO_EXEC_MODULES:
            for py_file in _collect_python_files(module_dir):
                tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
                for node in ast.walk(tree):
                    for name in _get_call_names(node):
                        if name in DANGEROUS_CALLS:
                            rel = py_file.relative_to(SRC_ROOT)
                            violations.append(f"{rel}:{node.lineno} — {name}()")

        assert not violations, "Direct execution calls found in restricted modules:\n" + "\n".join(
            f"  {v}" for v in violations
        )

    @pytest.mark.safety
    def test_no_os_exec_imports_in_channels(self) -> None:
        """Channel modules must not import subprocess or os.exec*."""
        violations: list[str] = []
        channel_dir = SRC_ROOT / "channels"
        for py_file in _collect_python_files(channel_dir):
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "subprocess":
                            rel = py_file.relative_to(SRC_ROOT)
                            violations.append(f"{rel}:{node.lineno} — import subprocess")
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.module.startswith("subprocess"):
                        rel = py_file.relative_to(SRC_ROOT)
                        violations.append(f"{rel}:{node.lineno} — from {node.module}")

        assert not violations, "Subprocess imports found in channel modules:\n" + "\n".join(
            f"  {v}" for v in violations
        )


# ---------------------------------------------------------------------------
# #146: Injection only through allowed modules
# ---------------------------------------------------------------------------


class TestInjectionPathRestriction:
    """PTY injection must only occur through adapter and executor modules."""

    @pytest.mark.safety
    def test_inject_reply_only_in_allowed_modules(self) -> None:
        """inject_reply() calls must only appear in allowed modules."""
        violations: list[str] = []
        for py_file in SRC_ROOT.rglob("*.py"):
            rel = str(py_file.relative_to(SRC_ROOT))
            if rel in ALLOWED_INJECTION_MODULES:
                continue
            # Skip test files
            if "test" in rel:
                continue

            source = py_file.read_text(encoding="utf-8")
            if "inject_reply" not in source:
                continue

            tree = ast.parse(source, filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    if isinstance(func, ast.Attribute) and func.attr == "inject_reply":
                        violations.append(f"{rel}:{node.lineno}")

        assert not violations, "inject_reply() called outside allowed modules:\n" + "\n".join(
            f"  {v}" for v in violations
        )


# ---------------------------------------------------------------------------
# #146: Gate evaluation guards all channel replies
# ---------------------------------------------------------------------------


class TestGateEnforcement:
    """All channel reply paths must flow through gate evaluation."""

    @pytest.mark.safety
    def test_router_calls_evaluate_gate(self) -> None:
        """PromptRouter.handle_reply must call _evaluate_gate before injection."""
        router_file = SRC_ROOT / "core" / "routing" / "router.py"
        source = router_file.read_text(encoding="utf-8")

        # The router must contain _evaluate_gate call
        assert "_evaluate_gate" in source, "PromptRouter missing _evaluate_gate call"

        # The gate module must exist
        gate_file = SRC_ROOT / "core" / "gate" / "engine.py"
        assert gate_file.exists(), "Gate engine module missing"

    @pytest.mark.safety
    def test_gate_engine_has_identity_check(self) -> None:
        """Gate engine must check channel identity against allowlist."""
        gate_file = SRC_ROOT / "core" / "gate" / "engine.py"
        source = gate_file.read_text(encoding="utf-8")
        assert "identity_allowlist" in source, "Gate engine missing identity allowlist check"

    @pytest.mark.safety
    def test_gate_engine_has_state_check(self) -> None:
        """Gate engine must check conversation state before allowing injection."""
        gate_file = SRC_ROOT / "core" / "gate" / "engine.py"
        source = gate_file.read_text(encoding="utf-8")
        assert "conversation_state" in source, "Gate engine missing conversation state check"

    @pytest.mark.safety
    def test_chat_mode_requires_gate(self) -> None:
        """Chat mode handler must be gated — no ungated chat injection.

        Verifies that within the handle_reply method body,
        _evaluate_gate is called before _chat_mode_handler.
        """
        router_file = SRC_ROOT / "core" / "routing" / "router.py"
        source = router_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(router_file))

        # Find the handle_reply method
        for node in ast.walk(tree):
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                if node.name == "handle_reply":
                    # Collect call order within this method
                    gate_line = None
                    chat_line = None
                    for child in ast.walk(node):
                        if isinstance(child, ast.Attribute):
                            if child.attr == "_evaluate_gate" and gate_line is None:
                                gate_line = child.lineno
                            if child.attr == "_chat_mode_handler" and chat_line is None:
                                chat_line = child.lineno
                    assert gate_line is not None, "handle_reply missing _evaluate_gate call"
                    if chat_line is not None:
                        assert gate_line < chat_line, (
                            "Gate evaluation must occur before chat mode handler "
                            f"in handle_reply (gate={gate_line}, chat={chat_line})"
                        )
                    break
        else:
            pytest.fail("handle_reply method not found in router")


# ---------------------------------------------------------------------------
# #146: Cloud module isolation (already partially tested elsewhere)
# ---------------------------------------------------------------------------


class TestCloudIsolation:
    """Cloud module must have no execution capability."""

    @pytest.mark.safety
    def test_cloud_module_no_network_imports(self) -> None:
        """Cloud module must not import networking libraries."""
        cloud_dir = SRC_ROOT / "cloud"
        if not cloud_dir.exists():
            pytest.skip("No cloud module present")

        forbidden = {"httpx", "requests", "aiohttp", "urllib3", "websockets", "socket"}
        violations: list[str] = []
        for py_file in _collect_python_files(cloud_dir):
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in forbidden:
                            rel = py_file.relative_to(SRC_ROOT)
                            violations.append(f"{rel}:{node.lineno} — import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.module.split(".")[0] in forbidden:
                        rel = py_file.relative_to(SRC_ROOT)
                        violations.append(f"{rel}:{node.lineno} — from {node.module}")

        assert not violations, "Network imports found in cloud module:\n" + "\n".join(
            f"  {v}" for v in violations
        )


# ---------------------------------------------------------------------------
# #147: Phone-first interaction model — reply parsing is deterministic
# ---------------------------------------------------------------------------


class TestPhoneFirstInteraction:
    """All interactive flows must be operable via plain text replies."""

    @pytest.mark.safety
    def test_numbered_choice_normalization_exists(self) -> None:
        """Numbered choice normalization must exist for text-only interaction."""
        from atlasbridge.core.interaction.normalizer import BinaryMenu, normalize_reply

        menu = BinaryMenu(yes_option="1", no_option="2", yes_label="Allow", no_label="Deny")
        # "1" should normalize to the yes_option
        result = normalize_reply(menu, "1")
        assert result is not None

    @pytest.mark.safety
    def test_yes_no_normalization(self) -> None:
        """Yes/no replies must normalize deterministically."""
        from atlasbridge.core.interaction.normalizer import BinaryMenu, normalize_reply

        menu = BinaryMenu(yes_option="y", no_option="n", yes_label="Yes", no_label="No")
        for yes_input in ("y", "yes", "Y", "YES"):
            assert normalize_reply(menu, yes_input) is not None, f"{yes_input!r} failed"
        for no_input in ("n", "no", "N", "NO"):
            assert normalize_reply(menu, no_input) is not None, f"{no_input!r} failed"

    @pytest.mark.safety
    def test_reply_always_appends_cr(self) -> None:
        """Remotely-operable injection plans must append CR for PTY semantics.

        RAW_TERMINAL is excluded — it represents unparsable interactive prompts
        that cannot be handled remotely and are escalated to the human operator.
        """
        from atlasbridge.core.interaction.plan import InteractionClass, build_plan

        for ic in InteractionClass:
            if ic == InteractionClass.RAW_TERMINAL:
                continue  # RAW_TERMINAL intentionally has append_cr=False
            plan = build_plan(ic)
            assert plan.append_cr is True, f"{ic.name} plan missing append_cr"


# ---------------------------------------------------------------------------
# #149: Boundary messaging — no secrets in messages
# ---------------------------------------------------------------------------


class TestBoundaryMessaging:
    """Boundary messages must never leak secrets."""

    @pytest.mark.safety
    def test_sanitize_strips_tokens(self) -> None:
        """Dashboard sanitizer strips tokens from displayed text."""
        from atlasbridge.dashboard.sanitize import redact_tokens

        dirty = "Bot token: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz_123456789"
        clean = redact_tokens(dirty)
        assert "ABCdefGHI" not in clean
        assert "[REDACTED:" in clean  # labeled redaction format

    @pytest.mark.safety
    def test_safe_excerpt_redacts_before_truncation(self) -> None:
        """safe_excerpt must redact secrets before truncating."""
        from atlasbridge.core.audit.writer import safe_excerpt

        secret = "sk-" + "A" * 40
        text = f"Here is a key: {secret} end"
        excerpt = safe_excerpt(text)
        assert secret not in excerpt


# ---------------------------------------------------------------------------
# #148: Docs-lint — no cloud execution language in user-facing docs
# ---------------------------------------------------------------------------

DOCS_ROOT = Path(__file__).parents[2] / "docs"

# Phrases that imply AtlasBridge has cloud execution capability.
# These must not appear in user-facing documentation (case-insensitive).
_CLOUD_EXEC_PHRASES = [
    r"cloud\s+execut",
    r"remote\s+run",
    r"run\s+(?:commands?\s+)?(?:on|in)\s+(?:the\s+)?cloud",
    r"server[\s-]side\s+execut",
    r"hosted\s+execut",
]

# Files that are explicitly about cloud/SaaS design or architecture and are
# allowed to mention cloud execution in a planning/prohibition context.
_ALLOWED_CLOUD_DOCS = {
    "saas-alpha-roadmap.md",
    "cloud-spec.md",
    "console.md",
    "enterprise-saas-architecture.md",
    "enterprise-trust-boundaries.md",
    "positioning-v1.md",
    "roadmap-90-days.md",
    "threat-model.md",
    "phone-first-interaction.md",
}


class TestDocsNoCloudExecLanguage:
    """User-facing docs must not imply cloud execution capability (#148)."""

    @pytest.mark.safety
    def test_no_cloud_execution_language(self) -> None:
        """Grep guard: no 'cloud execution' or 'remote run' in user-facing docs."""
        violations: list[str] = []
        combined = re.compile("|".join(_CLOUD_EXEC_PHRASES), re.IGNORECASE)

        for md_file in sorted(DOCS_ROOT.glob("*.md")):
            if md_file.name in _ALLOWED_CLOUD_DOCS:
                continue
            text = md_file.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), 1):
                if combined.search(line):
                    violations.append(f"{md_file.name}:{i} — {line.strip()[:80]}")

        assert not violations, "Cloud execution language found in user-facing docs:\n" + "\n".join(
            f"  {v}" for v in violations
        )


# ---------------------------------------------------------------------------
# #149: Boundary message templates for all channels
# ---------------------------------------------------------------------------


class TestBoundaryMessageTemplates:
    """All gate rejection reasons must have message templates (#149)."""

    @pytest.mark.safety
    def test_every_reject_reason_has_headline(self) -> None:
        """Every GateRejectReason must have a headline message."""
        from atlasbridge.core.gate.engine import GateRejectReason
        from atlasbridge.core.gate.messages import _REJECT_HEADLINES

        for reason in GateRejectReason:
            assert reason in _REJECT_HEADLINES, f"Missing headline for {reason.name}"

    @pytest.mark.safety
    def test_every_reject_reason_has_next_action(self) -> None:
        """Every GateRejectReason must have a next-action hint."""
        from atlasbridge.core.gate.engine import GateRejectReason
        from atlasbridge.core.gate.messages import _REJECT_NEXT_ACTIONS

        for reason in GateRejectReason:
            assert reason in _REJECT_NEXT_ACTIONS, f"Missing next action for {reason.name}"

    @pytest.mark.safety
    def test_no_active_session_message_includes_start_command(self) -> None:
        """The 'no active session' boundary message must tell users how to start."""
        from atlasbridge.core.gate.engine import GateRejectReason
        from atlasbridge.core.gate.messages import _REJECT_NEXT_ACTIONS

        action = _REJECT_NEXT_ACTIONS[GateRejectReason.REJECT_NO_ACTIVE_SESSION]
        assert "atlasbridge run" in action

    @pytest.mark.safety
    def test_boundary_messages_have_no_button_references(self) -> None:
        """Boundary messages must not reference taps or buttons."""
        from atlasbridge.core.gate.messages import _REJECT_HEADLINES, _REJECT_NEXT_ACTIONS

        forbidden = {"tap", "click", "button", "press the"}
        for reason, headline in _REJECT_HEADLINES.items():
            for word in forbidden:
                assert word not in headline.lower(), f"{reason.name} headline contains '{word}'"
        for reason, action in _REJECT_NEXT_ACTIONS.items():
            for word in forbidden:
                assert word not in action.lower(), f"{reason.name} next action contains '{word}'"


# ---------------------------------------------------------------------------
# #150: No production imports from cloud/enterprise execution modules
# ---------------------------------------------------------------------------


class TestSaasGateGuard:
    """No production code may import cloud execution modules (#150)."""

    @pytest.mark.safety
    def test_no_cloud_imports_in_production_code(self) -> None:
        """Production modules must not import from cloud execution paths."""
        # Enterprise and cloud modules are design-only stubs.
        # No production module should import from them except the CLI
        # surface that exposes enterprise commands (which are also stubs).
        forbidden_prefixes = {"atlasbridge.cloud", "atlasbridge.enterprise"}
        # CLI enterprise module is the stub surface — allowed to import stubs.
        # Dashboard settings page reads detect_edition() for display only.
        allowed_importers = {
            "cli/_enterprise.py",
            "cli/_edition_cmd.py",
            "dashboard/app.py",
            "dashboard/_collect.py",
            "dashboard/routers/core.py",
            "dashboard/routers/enterprise.py",
        }
        violations: list[str] = []

        for py_file in SRC_ROOT.rglob("*.py"):
            rel = str(py_file.relative_to(SRC_ROOT))
            # Skip cloud and enterprise modules themselves
            if rel.startswith("cloud/") or rel.startswith("enterprise/"):
                continue
            # Skip __pycache__
            if "__pycache__" in rel:
                continue
            # Skip allowed importers (CLI stubs)
            if rel in allowed_importers:
                continue

            source = py_file.read_text(encoding="utf-8")
            try:
                tree = ast.parse(source, filename=str(py_file))
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    for prefix in forbidden_prefixes:
                        if node.module.startswith(prefix):
                            violations.append(f"{rel}:{node.lineno} — from {node.module}")

        assert not violations, "Production code imports cloud/enterprise modules:\n" + "\n".join(
            f"  {v}" for v in violations
        )
