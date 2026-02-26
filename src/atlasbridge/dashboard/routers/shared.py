"""Shared router — reserved for future cross-edition utilities.

Currently empty. Do not add routes here without updating the edition contract
and the route freeze tests in tests/safety/test_dashboard_route_freeze.py.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()
