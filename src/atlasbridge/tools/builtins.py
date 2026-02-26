"""
Built-in tools for LLM chat mode.

These tools give the LLM basic file system and shell access,
governed by AtlasBridge's policy engine.

Risk levels:
  safe      — read-only operations, no side effects
  moderate  — write operations that modify files
  dangerous — shell execution, arbitrary code
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from atlasbridge.tools.registry import Tool


async def _read_file(args: dict[str, Any]) -> str:
    """Read the contents of a file."""
    path = args.get("path", "")
    if not path:
        return "Error: 'path' argument is required."
    p = Path(path).expanduser()
    if not p.exists():
        return f"Error: File not found: {path}"
    if not p.is_file():
        return f"Error: Not a file: {path}"
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        if len(content) > 50_000:
            content = content[:50_000] + "\n...(truncated at 50,000 chars)"
        return content
    except OSError as exc:
        return f"Error reading file: {exc}"


async def _list_directory(args: dict[str, Any]) -> str:
    """List the contents of a directory."""
    path = args.get("path", ".")
    p = Path(path).expanduser()
    if not p.exists():
        return f"Error: Directory not found: {path}"
    if not p.is_dir():
        return f"Error: Not a directory: {path}"
    try:
        entries = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        lines: list[str] = []
        for entry in entries[:200]:
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{entry.name}{suffix}")
        if len(entries) > 200:
            lines.append(f"... and {len(entries) - 200} more entries")
        return "\n".join(lines)
    except OSError as exc:
        return f"Error listing directory: {exc}"


async def _search_files(args: dict[str, Any]) -> str:
    """Search for files containing a pattern."""
    pattern = args.get("pattern", "")
    path = args.get("path", ".")
    if not pattern:
        return "Error: 'pattern' argument is required."

    p = Path(path).expanduser()
    if not p.exists():
        return f"Error: Path not found: {path}"

    try:
        proc = await asyncio.create_subprocess_exec(
            "grep",
            "-rl",
            "--include=*",
            "-m",
            "1",
            pattern,
            str(p),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        matches = stdout.decode("utf-8", errors="replace").strip()
        if not matches:
            return f"No files found containing '{pattern}' in {path}"
        lines = matches.split("\n")[:50]
        result = "\n".join(lines)
        if len(matches.split("\n")) > 50:
            result += "\n... (truncated)"
        return result
    except TimeoutError:
        return "Error: Search timed out after 10 seconds."
    except FileNotFoundError:
        return "Error: 'grep' not found. Search requires grep to be installed."
    except OSError as exc:
        return f"Error searching files: {exc}"


async def _write_file(args: dict[str, Any]) -> str:
    """Write content to a file."""
    path = args.get("path", "")
    content = args.get("content", "")
    if not path:
        return "Error: 'path' argument is required."
    p = Path(path).expanduser()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} chars to {path}"
    except OSError as exc:
        return f"Error writing file: {exc}"


async def _run_command(args: dict[str, Any]) -> str:
    """Execute a shell command."""
    command = args.get("command", "")
    cwd = args.get("cwd", os.getcwd())
    if not command:
        return "Error: 'command' argument is required."

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
        output = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")

        result_parts: list[str] = []
        if output:
            result_parts.append(output)
        if err:
            result_parts.append(f"STDERR:\n{err}")
        result_parts.append(f"Exit code: {proc.returncode}")

        result = "\n".join(result_parts)
        if len(result) > 20_000:
            result = result[:20_000] + "\n...(truncated)"
        return result
    except TimeoutError:
        return "Error: Command timed out after 30 seconds."
    except OSError as exc:
        return f"Error running command: {exc}"


def get_builtin_tools() -> list[Tool]:
    """Return all built-in tools."""
    return [
        Tool(
            name="read_file",
            description="Read the contents of a file at the given path.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative file path"},
                },
                "required": ["path"],
            },
            risk_level="safe",
            executor=_read_file,
        ),
        Tool(
            name="list_directory",
            description="List files and subdirectories in a directory.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path (default: current directory)",
                        "default": ".",
                    },
                },
            },
            risk_level="safe",
            executor=_list_directory,
        ),
        Tool(
            name="search_files",
            description="Search for files containing a text pattern (uses grep).",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Text pattern to search for"},
                    "path": {
                        "type": "string",
                        "description": "Directory to search in (default: current directory)",
                        "default": ".",
                    },
                },
                "required": ["pattern"],
            },
            risk_level="safe",
            executor=_search_files,
        ),
        Tool(
            name="write_file",
            description="Write content to a file, creating it if it doesn't exist.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to write to"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["path", "content"],
            },
            risk_level="moderate",
            executor=_write_file,
        ),
        Tool(
            name="run_command",
            description="Execute a shell command and return its output.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                    "cwd": {
                        "type": "string",
                        "description": "Working directory (default: current directory)",
                    },
                },
                "required": ["command"],
            },
            risk_level="dangerous",
            executor=_run_command,
        ),
    ]
