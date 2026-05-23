"""Pytest configuration for integration tests.

Integration tests are allowed to make real network requests, so socket access
is explicitly re-enabled here after being blocked globally in pyproject.toml.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _allow_network(socket_enabled):
    """Re-enable real socket access for every test in this directory tree.

    The global ``--disable-socket`` configured in pyproject.toml blocks all
    network I/O in unit tests.  Integration tests need actual HTTP to reach
    the external APIs they exercise, so this autouse fixture re-enables
    sockets for everything under ``tests/integration/``.
    """
