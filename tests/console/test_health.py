"""Tests for SystemHealth enum and compute_health() logic."""

from __future__ import annotations

import pytest

from atlasbridge.console.supervisor import ProcessInfo, SystemHealth, compute_health


# ---------------------------------------------------------------------------
# SystemHealth enum
# ---------------------------------------------------------------------------


class TestSystemHealthEnum:
    def test_enum_values(self):
        assert SystemHealth.GREEN.value == "green"
        assert SystemHealth.YELLOW.value == "yellow"
        assert SystemHealth.RED.value == "red"


# ---------------------------------------------------------------------------
# compute_health — process-only scenarios
# ---------------------------------------------------------------------------


class TestComputeHealthProcesses:
    def test_all_running_no_doctor(self):
        statuses = [
            ProcessInfo(name="daemon", running=True, pid=100),
            ProcessInfo(name="dashboard", running=True, pid=101),
            ProcessInfo(name="agent", running=True, pid=102),
        ]
        assert compute_health(statuses) == SystemHealth.GREEN

    def test_nothing_running(self):
        statuses = [
            ProcessInfo(name="daemon", running=False),
            ProcessInfo(name="dashboard", running=False),
            ProcessInfo(name="agent", running=False),
        ]
        assert compute_health(statuses) == SystemHealth.YELLOW

    def test_daemon_down_agent_running(self):
        statuses = [
            ProcessInfo(name="daemon", running=False),
            ProcessInfo(name="dashboard", running=False),
            ProcessInfo(name="agent", running=True, pid=102),
        ]
        assert compute_health(statuses) == SystemHealth.RED

    def test_empty_statuses(self):
        assert compute_health([]) == SystemHealth.YELLOW

    def test_daemon_only_running(self):
        statuses = [
            ProcessInfo(name="daemon", running=True, pid=100),
            ProcessInfo(name="dashboard", running=False),
            ProcessInfo(name="agent", running=False),
        ]
        assert compute_health(statuses) == SystemHealth.GREEN


# ---------------------------------------------------------------------------
# compute_health — with doctor checks
# ---------------------------------------------------------------------------


class TestComputeHealthDoctor:
    def test_doctor_fail_returns_red(self):
        statuses = [ProcessInfo(name="daemon", running=True, pid=100)]
        checks = [{"name": "config", "status": "fail"}]
        assert compute_health(statuses, doctor_checks=checks) == SystemHealth.RED

    def test_doctor_warn_returns_yellow(self):
        statuses = [ProcessInfo(name="daemon", running=True, pid=100)]
        checks = [{"name": "config", "status": "warn"}]
        assert compute_health(statuses, doctor_checks=checks) == SystemHealth.YELLOW

    def test_all_running_with_passing_doctor(self):
        statuses = [
            ProcessInfo(name="daemon", running=True, pid=100),
            ProcessInfo(name="agent", running=True, pid=101),
        ]
        checks = [
            {"name": "config", "status": "pass"},
            {"name": "database", "status": "pass"},
        ]
        assert compute_health(statuses, doctor_checks=checks) == SystemHealth.GREEN

    def test_doctor_fail_overrides_running(self):
        """Doctor failure is RED even when all processes are running."""
        statuses = [
            ProcessInfo(name="daemon", running=True, pid=100),
            ProcessInfo(name="dashboard", running=True, pid=101),
            ProcessInfo(name="agent", running=True, pid=102),
        ]
        checks = [{"name": "db", "status": "fail"}]
        assert compute_health(statuses, doctor_checks=checks) == SystemHealth.RED
