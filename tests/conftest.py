"""Shared fixtures for Suivi de Colis tests."""

import socket
import sys

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

if sys.platform == "win32":
    # asyncio's self-pipe uses socket.socketpair(), which on Windows falls back to
    # AF_INET sockets that pytest-socket blocks. Allow just that internal pair.
    _real_socket = socket.socket
    _real_socketpair = socket.socketpair

    def _socketpair(*args, **kwargs):
        guarded = socket.socket
        socket.socket = _real_socket
        try:
            return _real_socketpair(*args, **kwargs)
        finally:
            socket.socket = guarded

    socket.socketpair = _socketpair


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components/ in every test."""
    yield


@pytest.fixture(autouse=True)
def skip_frontend_dependencies(hass):
    """Pretend the manifest dependencies are loaded (no frontend build in tests)."""
    hass.config.components.update({"frontend", "http"})
    yield
