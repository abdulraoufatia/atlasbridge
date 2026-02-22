"""Tests for dashboard FastAPI server endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")


class TestHomeEndpoint:
    def test_home_returns_200(self, client):
        response = client.get("/")
        assert response.status_code == 200

    def test_home_contains_banner(self, client):
        response = client.get("/")
        assert "READ-ONLY GOVERNANCE VIEW" in response.text

    def test_home_shows_stats(self, client):
        response = client.get("/")
        assert "Total Sessions" in response.text

    def test_home_shows_sessions(self, client):
        response = client.get("/")
        assert "sess-001" in response.text


class TestSessionDetailEndpoint:
    def test_session_detail_returns_200(self, client):
        response = client.get("/sessions/sess-001")
        assert response.status_code == 200

    def test_session_detail_shows_prompts(self, client):
        response = client.get("/sessions/sess-001")
        assert "prompt-001" in response.text

    def test_session_detail_not_found(self, client):
        response = client.get("/sessions/nonexistent")
        assert response.status_code == 200
        assert "not found" in response.text.lower()


class TestTraceDetailEndpoint:
    def test_trace_detail_returns_200(self, client):
        response = client.get("/traces/0")
        assert response.status_code == 200

    def test_trace_detail_not_found(self, client):
        response = client.get("/traces/999")
        assert response.status_code == 200
        assert "not found" in response.text.lower()


class TestIntegrityEndpoint:
    def test_integrity_returns_200(self, client):
        response = client.get("/integrity")
        assert response.status_code == 200

    def test_integrity_shows_status(self, client):
        response = client.get("/integrity")
        assert "VALID" in response.text


class TestIntegrityApiEndpoint:
    def test_verify_returns_json(self, client):
        response = client.post("/api/integrity/verify")
        assert response.status_code == 200
        data = response.json()
        assert "trace" in data
        assert "audit" in data
        assert data["trace"]["valid"] is True


class TestStaticAssets:
    def test_css_served(self, client):
        response = client.get("/static/style.css")
        assert response.status_code == 200
        assert "text/css" in response.headers.get("content-type", "")


class TestNoDataState:
    def test_home_with_no_db(self, tmp_path):
        from atlasbridge.dashboard.app import create_app
        from starlette.testclient import TestClient

        app = create_app(
            db_path=tmp_path / "missing.db",
            trace_path=tmp_path / "missing.jsonl",
        )
        client = TestClient(app)
        response = client.get("/")
        assert response.status_code == 200
        assert "No data yet" in response.text
