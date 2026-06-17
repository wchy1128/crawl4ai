"""
Tests for MCP Streamable HTTP transport (MCP 2025-03-26).

Two test layers:

1. Static structure tests — verify mcp_bridge.py declares the Streamable HTTP
   handler. No server, no mcp runtime. Mirrors the pattern in
   tests/test_issue_1850_mcp_sse.py (which guards the SSE counterpart).

2. End-to-end demo — connect to a running server with the mcp client library.
   Run manually (the file doubles as a script):

       cd deploy/docker && uvicorn server:app --port 8020 &
       python tests/mcp/test_mcp_streamable_http.py
"""

import pytest


# -- Static structure tests (no server needed) --

class TestMCPBridgeStreamableHandler:
    """Verify mcp_bridge.py wires Streamable HTTP correctly."""

    def test_mcp_bridge_has_streamable_http_import(self):
        with open("deploy/docker/mcp_bridge.py", encoding="utf-8") as f:
            source = f.read()
        assert "from mcp.server.streamable_http_manager import" in source

    def test_mcp_bridge_has_streamable_http_handler(self):
        with open("deploy/docker/mcp_bridge.py", encoding="utf-8") as f:
            source = f.read()
        # callable class — same trick as _MCPSseApp, see #1850
        assert "class _MCPStreamableApp" in source
        assert "async def __call__(self, scope, receive, send)" in source
        assert "_MCPStreamableApp()" in source

    def test_mcp_bridge_uses_session_manager(self):
        with open("deploy/docker/mcp_bridge.py", encoding="utf-8") as f:
            source = f.read()
        assert "StreamableHTTPSessionManager(" in source
        # stateful mode (not stateless=True)
        assert "stateless=False" in source

    def test_mcp_bridge_attaches_base_route(self):
        with open("deploy/docker/mcp_bridge.py", encoding="utf-8") as f:
            source = f.read()
        # Route at exact base path (e.g. "/mcp"), not a sub-path
        assert 'Route(f"{base}", endpoint=_MCPStreamableApp())' in source

    def test_mcp_bridge_returns_session_manager(self):
        with open("deploy/docker/mcp_bridge.py", encoding="utf-8") as f:
            source = f.read()
        assert "-> StreamableHTTPSessionManager" in source
        assert "return session_manager" in source


class TestServerLifespanIntegration:
    """Verify server.py wraps lifespan yield in session_manager.run()."""

    def test_server_imports_session_manager_type(self):
        with open("deploy/docker/server.py", encoding="utf-8") as f:
            source = f.read()
        assert "StreamableHTTPSessionManager" in source

    def test_server_calls_run_in_lifespan(self):
        with open("deploy/docker/server.py", encoding="utf-8") as f:
            source = f.read()
        assert "async with _session_manager.run():" in source

    def test_server_assigns_attach_mcp_result(self):
        with open("deploy/docker/server.py", encoding="utf-8") as f:
            source = f.read()
        assert "_session_manager = attach_mcp(" in source


# -- End-to-end demo (run manually as a script) --

async def _e2e_demo():
    """Connect to a running server at 127.0.0.1:8020 and list tools."""
    from mcp.client.streamable_http import streamablehttp_client
    from mcp.client.session import ClientSession

    url = "http://127.0.0.1:8020/mcp"
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as sess:
            await sess.initialize()
            tools = await sess.list_tools()
            names = sorted(t.name for t in tools.tools)
            print(f"OK: connected via Streamable HTTP, {len(names)} tools: {names}")
            return names


if __name__ == "__main__":
    import asyncio
    names = asyncio.run(_e2e_demo())
    # Sanity: c4ai registers these as MCP tools (see server.py @mcp_tool decorators)
    expected = {"md", "html", "screenshot", "pdf", "execute_js", "crawl", "ask"}
    missing = expected - set(names)
    assert not missing, f"missing expected tools: {missing}"
    print("All expected MCP tools present.")
