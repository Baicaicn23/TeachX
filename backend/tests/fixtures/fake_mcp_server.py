"""测试夹具:最小 MCP stdio server(换行分隔 JSON-RPC 2.0)。

提供 fake_echo 工具,用于在不引外部依赖的情况下测试 TeachX 的 MCP 客户端。
"""
from __future__ import annotations

import json
import sys


def respond(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = req.get("method")
        if method is None:
            continue  # notification,无需回应

        if method == "initialize":
            respond(
                {
                    "jsonrpc": "2.0",
                    "id": req["id"],
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "fake-mcp", "version": "0.0.1"},
                    },
                }
            )
        elif method == "tools/list":
            respond(
                {
                    "jsonrpc": "2.0",
                    "id": req["id"],
                    "result": {
                        "tools": [
                            {
                                "name": "fake_echo",
                                "description": "原样返回输入文本,用于测试",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"text": {"type": "string"}},
                                    "required": ["text"],
                                },
                            }
                        ]
                    },
                }
            )
        elif method == "tools/call":
            name = req.get("params", {}).get("name", "")
            args = req.get("params", {}).get("arguments", {}) or {}
            if name == "fake_echo":
                respond(
                    {
                        "jsonrpc": "2.0",
                        "id": req["id"],
                        "result": {
                            "content": [
                                {"type": "text", "text": "echo:" + str(args.get("text", ""))}
                            ],
                            "isError": False,
                        },
                    }
                )
            else:
                respond(
                    {
                        "jsonrpc": "2.0",
                        "id": req["id"],
                        "result": {
                            "content": [{"type": "text", "text": f"unknown tool {name}"}],
                            "isError": True,
                        },
                    }
                )
        else:
            respond(
                {
                    "jsonrpc": "2.0",
                    "id": req.get("id"),
                    "error": {"code": -32601, "message": f"method not found: {method}"},
                }
            )


if __name__ == "__main__":
    main()
