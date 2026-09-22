"""Optional MCP entrypoint contracts."""

from __future__ import annotations

import pytest


def test_build_server_accepts_supported_mcp_api():
    pytest.importorskip("mcp")

    from chstockdata.mcp_server import build_server

    assert build_server() is not None
