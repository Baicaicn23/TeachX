"""回合 trace 分析(学习版)。

TeachX 的每个回合本来就持久化了完整事件流(带序号、时间戳和逐层元数据),
事件流就是 trace。本模块是读它的放大镜:把一回合的事件归纳成一份诊断报告,
把失败定位到五层之一——模型 / 检索 / 工具 / 编排 / 费用。

用法(在 backend/ 目录下,分析本地数据库里某个会话的最后一回合):

    uv run python -m teachx.runtime.turn_trace --session <会话id>
    uv run python -m teachx.runtime.turn_trace --session <会话id> --message <消息id>
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any

_LAYER_NAMES = {
    "model": "模型层",
    "retrieval": "检索层",
    "tool": "工具层",
    "orchestration": "编排层",
    "cost": "费用层",
    "unknown": "未知层",
}

# 错误码到责任层的映射。没列到的错误码归"未知层",不猜。
_ERROR_LAYERS = {
    "provider_timeout": "model",
    "rate_limited": "model",
    "provider_connection_error": "model",
    "provider_server_error": "model",
    "provider_http_error": "model",
    "stream_interrupted": "model",
    "turn_timeout": "orchestration",
    "max_rounds_exceeded": "orchestration",
    "runtime_error": "orchestration",
    "daily_budget_exceeded": "cost",
    "tool_execution_in_progress": "tool",
}

RETRIEVAL_TOOL = "knowledge_search"


def attribute_error_code(error_code: str) -> str:
    """把稳定错误码映射到责任层;未知代码返回 unknown,不做猜测。"""
    return _ERROR_LAYERS.get(error_code, "unknown")


def _metadata(event: dict[str, Any]) -> dict[str, Any]:
    value = event.get("metadata")
    return value if isinstance(value, dict) else {}


def analyze_turn_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    """把一回合的事件流归纳为诊断报告。"""
    findings: list[dict[str, Any]] = []
    tool_rows: list[dict[str, Any]] = []
    done_meta: dict[str, Any] | None = None

    for event in events:
        event_type = str(event.get("type") or "")
        meta = _metadata(event)

        if event_type == "done":
            done_meta = meta

        if event_type == "error":
            error_code = str(meta.get("error_code") or "unknown")
            layer = attribute_error_code(error_code)
            findings.append(
                {
                    "severity": "error",
                    "layer": layer,
                    "code": error_code,
                    "detail": str(event.get("content") or ""),
                }
            )

        if event_type == "tool_result":
            tool = str(meta.get("tool") or "")
            call_id = str(meta.get("call_id") or "")
            success = bool(meta.get("success"))
            layer = "retrieval" if tool == RETRIEVAL_TOOL else "tool"
            tool_rows.append(
                {
                    "call_id": call_id,
                    "tool": tool,
                    "success": success,
                    "attempt_count": int(meta.get("attempt_count") or 0),
                    "retry_count": int(meta.get("retry_count") or 0),
                    "duration_ms": meta.get("duration_ms"),
                }
            )
            if not success:
                code = str(meta.get("error_code") or "tool_error")
                findings.append(
                    {
                        "severity": "error",
                        "layer": layer,
                        "code": code,
                        "detail": f"{tool}({call_id}) 失败:{event.get('content') or ''}",
                    }
                )
            if int(meta.get("retry_count") or 0) > 0:
                outcome = "成功" if success else "仍失败"
                findings.append(
                    {
                        "severity": "warning",
                        "layer": layer,
                        "code": "tool_retried",
                        "detail": (
                            f"{tool}({call_id}) 重试 {meta.get('retry_count')} 次后{outcome}"
                        ),
                    }
                )
            if tool == RETRIEVAL_TOOL and meta.get("sources") == []:
                findings.append(
                    {
                        "severity": "warning",
                        "layer": "retrieval",
                        "code": "empty_retrieval",
                        "detail": f"{tool}({call_id}) 没有检索到任何资料",
                    }
                )
            if meta.get("context_truncated"):
                findings.append(
                    {
                        "severity": "warning",
                        "layer": "orchestration",
                        "code": "tool_context_truncated",
                        "detail": f"{tool}({call_id}) 结果过长,传给模型前被截断",
                    }
                )

    timestamps = [
        float(event["timestamp"]) for event in events if event.get("timestamp") is not None
    ]
    status = str(done_meta.get("status") or "unknown") if done_meta else "unknown"
    if done_meta is None:
        findings.append(
            {
                "severity": "warning",
                "layer": "orchestration",
                "code": "turn_not_finalized",
                "detail": "事件流里没有 done 事件(连接中断或进程退出)",
            }
        )

    return {
        "turn_id": events[0].get("turn_id") if events else None,
        "status": status,
        "partial": bool(done_meta.get("partial")) if done_meta else False,
        "rounds_used": int(done_meta.get("rounds_used") or 0) if done_meta else 0,
        "tool_call_count": (
            int(done_meta.get("tool_call_count") or 0) if done_meta else len(tool_rows)
        ),
        "duration_seconds": (
            round(max(timestamps) - min(timestamps), 2) if timestamps else 0.0
        ),
        "tools": tool_rows,
        "findings": findings,
    }


def render_trace(report: dict[str, Any]) -> str:
    """把诊断报告渲染成给人读的文本。"""
    lines = [
        "回合 trace"
        f"  turn={report['turn_id'] or '?'}"
        f"  状态={report['status']}"
        f"{'(部分回答)' if report['partial'] else ''}"
        f"  时长={report['duration_seconds']}s"
        f"  轮数={report['rounds_used']}"
        f"  工具调用={report['tool_call_count']}"
    ]
    for finding in report["findings"]:
        lines.append(
            f"[{finding['severity']}] {_LAYER_NAMES.get(finding['layer'], finding['layer'])}"
            f"  {finding['code']}  {finding['detail']}".rstrip()
        )
    for tool in report["tools"]:
        duration = tool["duration_ms"]
        duration_text = f"{duration:.0f}ms" if isinstance(duration, (int, float)) else "?"
        lines.append(
            f"工具 {tool['tool']}({tool['call_id']})"
            f" {'成功' if tool['success'] else '失败'}"
            f" 尝试 {tool['attempt_count']} 次 {duration_text}"
        )
    if not report["findings"]:
        lines.append("未发现异常")
    return "\n".join(lines)


async def _load_events(
    database_path: Path,
    session_id: str,
    message_id: int | None,
) -> list[dict[str, Any]]:
    from teachx.storage.database import Database
    from teachx.storage.repository import SessionRepository

    database = Database(database_path)
    repository = SessionRepository(database)
    if message_id is not None:
        events = await repository.message_events(session_id, message_id)
        if events:
            return events
        raise SystemExit(f"消息 {message_id} 没有事件(可能不是助手消息)")
    messages = await repository.get_messages(session_id)
    for message in reversed(messages):
        if message.role == "assistant" and message.events:
            return message.events
    raise SystemExit("该会话没有保存过回合事件")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="分析一个回合的持久化事件(trace)")
    parser.add_argument("--db", type=Path, default=None, help="数据库路径,默认读环境配置")
    parser.add_argument("--session", required=True, help="会话 id")
    parser.add_argument("--message", type=int, default=None, help="助手消息 id,默认取最后一条")
    args = parser.parse_args(argv)

    database_path = args.db
    if database_path is None:
        from teachx.config import get_settings

        database_path = get_settings().resolved_database_path()

    events = asyncio.run(_load_events(database_path, args.session, args.message))
    print(render_trace(analyze_turn_events(events)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
