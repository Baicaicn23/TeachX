from __future__ import annotations

import sys
from pathlib import Path

import pytest

from teachx.runtime.mcp_client import McpBridge, McpStdioClient
from teachx.runtime.tools import ToolRegistry

FIXTURE = Path(__file__).parent / "fixtures" / "fake_mcp_server.py"


def _client() -> McpStdioClient:
    return McpStdioClient([sys.executable, "-u", str(FIXTURE)], request_timeout=15.0)


@pytest.mark.asyncio
async def test_initialize_and_list_tools() -> None:
    client = _client()
    bridge = McpBridge("demo", client)
    try:
        await client.start()
        info = await client.initialize()
        assert info["name"] == "fake-mcp"
        tools = await client.list_tools()
        assert [t["name"] for t in tools] == ["fake_echo"]
        # 幂等 start:initialize 之后桥接不应重复拉起进程。
        registered = await bridge.register_into(ToolRegistry())
        assert registered == ["mcp_demo_fake_echo"]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_bridged_tool_executes_through_registry(tmp_path: Path) -> None:
    client = _client()
    bridge = McpBridge("demo", client)
    registry = ToolRegistry()
    try:
        await bridge.register_into(registry)
        tool = registry.get("mcp_demo_fake_echo")
        assert tool is not None
        # 协议/schema 正确透传给模型。
        schema = tool.schema()
        assert schema["function"]["name"] == "mcp_demo_fake_echo"
        assert schema["function"]["parameters"]["required"] == ["text"]
        # 保守政策:外部工具按有副作用、不重试处理。
        assert registry.is_read_only("mcp_demo_fake_echo") is False

        result = await registry.execute(
            "mcp_demo_fake_echo", {"text": "你好"}, call_id="c1"
        )
        assert result.success is True
        assert result.content == "echo:你好"
        assert result.metadata is not None
        assert result.metadata["mcp_server"] == "demo"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_remote_tool_error_becomes_failed_result() -> None:
    client = _client()
    bridge = McpBridge("demo", client)
    registry = ToolRegistry()
    try:
        await bridge.register_into(registry)
        result = await registry.execute(
            "mcp_demo_fake_echo",
            {"text": "x"},
            call_id="c1",
        )
        assert result.success is True
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_unknown_remote_tool_returns_failure(tmp_path: Path) -> None:
    """server 端标记 isError 时,注册表返回失败结果而不是抛异常炸回合。"""
    client = _client()
    bridge = McpBridge("demo", client)
    registry = ToolRegistry()
    try:
        await bridge.register_into(registry)
        tool = registry.get("mcp_demo_fake_echo")
        assert tool is not None
        # 直接绕过注册表,调用一个 server 不认识的远端工具名。
        from teachx.runtime.mcp_client import McpToolError

        with pytest.raises(McpToolError):
            await client.call_tool("no_such_tool", {})
    finally:
        await client.close()
