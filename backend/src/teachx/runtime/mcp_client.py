"""最小 MCP stdio 客户端与工具桥接(学习版)。

按 MCP 协议(基于 JSON-RPC 2.0、换行分隔帧)自写客户端,不引入 SDK:
initialize 握手 → tools/list 发现 → tools/call 执行。发现的远端工具由
McpBridge 包装成普通 BaseTool 注册进 ToolRegistry,Agent Loop 对此无感知。

命名约定:注册名前缀 `mcp_<server>_`,避免与内置工具或不同 server 之间重名。
外部工具一律按"有副作用"处理(read_only=False、不重试)——保守默认。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from teachx.runtime.tools import BaseTool, ToolPolicy, ToolResult


class McpError(RuntimeError):
    """MCP 请求失败(server 返回 error、响应超时或连接断开)。"""


class McpToolError(RuntimeError):
    """远端工具执行完成但标记了 isError。"""


class McpStdioClient:
    """与一个 MCP server 子进程通信的顺序客户端。"""

    def __init__(self, command: list[str], request_timeout: float = 20.0) -> None:
        self.command = command
        self.request_timeout = request_timeout
        self._process: asyncio.subprocess.Process | None = None
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._next_id = 1
        self._reader_task: asyncio.Task[None] | None = None
        self.server_info: dict[str, Any] = {}

    async def start(self) -> None:
        if self._process is not None:
            return  # 幂等:重复 start(例如 initialize 后再 register_into)不重复拉起进程
        self._process = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self._reader_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        assert self._process and self._process.stdout
        while True:
            line = await self._process.stdout.readline()
            if not line:
                break
            try:
                message = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                continue
            request_id = message.get("id")
            if request_id is None:
                continue  # notification
            future = self._pending.pop(int(request_id), None)
            if future and not future.done():
                future.set_result(message)
        # 连接关闭:唤醒所有等待者。
        for future in self._pending.values():
            if not future.done():
                future.set_exception(McpError("MCP server 连接已关闭"))
        self._pending.clear()

    async def _request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if not self._process or not self._process.stdin:
            raise McpError("MCP server 未启动")
        request_id = self._next_id
        self._next_id += 1
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        self._process.stdin.write(
            (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        )
        await self._process.stdin.drain()
        try:
            message = await asyncio.wait_for(future, timeout=self.request_timeout)
        except TimeoutError as exc:
            self._pending.pop(request_id, None)
            raise McpError(f"MCP 请求超时: {method}") from exc
        if "error" in message:
            raise McpError(f"MCP 错误: {message['error']}")
        return message.get("result")

    async def initialize(self) -> dict[str, Any]:
        result = await self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "teachx", "version": "0.1.0"},
            },
        )
        self.server_info = dict(result.get("serverInfo", {})) if result else {}
        # 协议要求:initialize 响应后发送 initialized 通知(无需回应)。
        if self._process and self._process.stdin:
            notice = {"jsonrpc": "2.0", "method": "notifications/initialized"}
            self._process.stdin.write(
                (json.dumps(notice, ensure_ascii=False) + "\n").encode("utf-8")
            )
            await self._process.stdin.drain()
        return self.server_info

    async def list_tools(self) -> list[dict[str, Any]]:
        result = await self._request("tools/list")
        return list(result.get("tools", [])) if result else []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        result = await self._request(
            "tools/call", {"name": name, "arguments": arguments}
        )
        content = (result or {}).get("content", [])
        text = "\n".join(
            str(item.get("text", "")) for item in content if item.get("type") == "text"
        )
        if (result or {}).get("isError"):
            raise McpToolError(text or f"工具 {name} 执行失败")
        return text

    async def close(self) -> None:
        if self._process and self._process.stdin:
            self._process.stdin.close()
        if self._process:
            self._process.terminate()
            await self._process.wait()
        if self._reader_task:
            self._reader_task.cancel()


class McpTool(BaseTool):
    """把一个远端 MCP 工具包装成本地 BaseTool。"""

    def __init__(
        self,
        *,
        server: str,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        client: McpStdioClient,
    ) -> None:
        self.server = server
        self.name = f"mcp_{server}_{name}"
        self.description = description or f"MCP 工具 {name}(来自 {server})"
        self.parameters = input_schema or {"type": "object", "properties": {}}
        self.client = client
        # 外部工具按保守政策处理:视作有副作用、不重试。
        self.policy = ToolPolicy(read_only=False, max_attempts=1, timeout_seconds=30.0)

    async def execute(
        self,
        context: Any = None,
        **kwargs: Any,
    ) -> ToolResult:
        del context
        text = await self.client.call_tool(self.remote_name, kwargs)
        return ToolResult(
            content=text,
            metadata={"mcp_server": self.server, "mcp_tool": self.remote_name},
        )

    @property
    def remote_name(self) -> str:
        # 注册名带 mcp_<server>_ 前缀,调用远端时要去掉。
        return self.name[len(f"mcp_{self.server}_") :]


class McpBridge:
    """连接一个 MCP server,把它的工具注册进本地 ToolRegistry。"""

    def __init__(self, server_name: str, client: McpStdioClient) -> None:
        self.server_name = server_name
        self.client = client

    async def register_into(self, registry: Any) -> list[str]:
        await self.client.start()
        await self.client.initialize()
        registered: list[str] = []
        for tool in await self.client.list_tools():
            name = str(tool.get("name") or "")
            if not name:
                continue
            wrapped = McpTool(
                server=self.server_name,
                name=name,
                description=str(tool.get("description") or ""),
                input_schema=dict(tool.get("inputSchema") or {}),
                client=self.client,
            )
            registry.register(wrapped)
            registered.append(wrapped.name)
        return registered
