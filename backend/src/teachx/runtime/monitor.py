"""在线监控聚合(学习版,P3)。

回合 trace(教程 23)回答"这一回合为什么坏";这里回答"系统最近整体表现
怎么样":扫持久化事件流,聚合回合数、失败率、工具失败率、空检索率、意图
分布、时延 P50/P95 与 token 消耗。数据全部来自已落库的事实(messages
事件 + done metadata),不采样、不估算。

用法(在 backend/ 目录下):

    # 最近 24 小时
    uv run python -m teachx.runtime.monitor

    # 指定时间窗(小时,0 = 全部)与数据库;--json 输出机器可读结果
    uv run python -m teachx.runtime.monitor --hours 168 --json
    uv run python -m teachx.runtime.monitor --db /tmp/teachx-demo.db
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

_LAYER_NAMES = {
    "model": "模型",
    "retrieval": "检索",
    "tool": "工具",
    "orchestration": "编排",
    "cost": "费用",
}

_INTENT_NAMES = {
    "concept_explain": "概念讲解",
    "practice": "练习",
    "progress": "进度",
    "retrieval": "资料检索",
    "calculation": "计算",
    "smalltalk": "闲聊/默认",
}


def percentile(values: list[float], ratio: float) -> float | None:
    """线性插值百分位(与常见监控系统的分位数语义一致);空返回 None。"""

    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    position = ratio * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    frac = position - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * frac, 3)


def _metadata(event: dict[str, Any]) -> dict[str, Any]:
    value = event.get("metadata")
    return value if isinstance(value, dict) else {}


def _turn_stats(events: list[dict[str, Any]]) -> dict[str, Any]:
    """把一个回合的事件流归纳成单回合统计。"""

    done_meta: dict[str, Any] = {}
    tool_calls = 0
    tool_failures = 0
    empty_retrievals = 0
    error_codes: list[str] = []
    timestamps = [
        float(event["timestamp"])
        for event in events
        if event.get("timestamp") is not None
    ]
    for event in events:
        meta = _metadata(event)
        event_type = str(event.get("type") or "")
        if event_type == "done":
            done_meta = meta
        elif event_type == "error":
            error_codes.append(str(meta.get("error_code") or "unknown"))
        elif event_type == "tool_result":
            tool_calls += 1
            if not meta.get("success"):
                tool_failures += 1
            if (
                str(meta.get("tool") or "") == "knowledge_search"
                and meta.get("sources") == []
            ):
                empty_retrievals += 1
    usage_summary = done_meta.get("usage_summary")
    total_tokens = (
        int(usage_summary.get("total_tokens", 0))
        if isinstance(usage_summary, dict)
        else 0
    )
    duration = (
        round(max(timestamps) - min(timestamps), 3) if timestamps else 0.0
    )
    return {
        "status": str(done_meta.get("status") or "unknown"),
        "intent": str(done_meta.get("intent") or "") or None,
        "partial": bool(done_meta.get("partial")),
        "tool_calls": tool_calls,
        "tool_failures": tool_failures,
        "empty_retrievals": empty_retrievals,
        "error_codes": error_codes,
        "total_tokens": total_tokens,
        "duration_seconds": duration,
    }


def aggregate_turns(turns: list[list[dict[str, Any]]]) -> dict[str, Any]:
    """把若干回合的事件流聚合成一份在线监控报告(纯函数)。"""

    stats = [_turn_stats(events) for events in turns]
    completed = sum(1 for stat in stats if stat["status"] == "completed")
    failed = sum(1 for stat in stats if stat["status"] == "failed")
    tool_calls = sum(stat["tool_calls"] for stat in stats)
    tool_failures = sum(stat["tool_failures"] for stat in stats)
    empty_retrievals = sum(stat["empty_retrievals"] for stat in stats)
    durations = [
        stat["duration_seconds"]
        for stat in stats
        if stat["duration_seconds"] > 0
    ]
    error_counter = Counter(
        code for stat in stats for code in stat["error_codes"]
    )
    intent_counter = Counter(
        stat["intent"] for stat in stats if stat["intent"]
    )
    turns_with_retrieval = sum(1 for stat in stats if stat["empty_retrievals"])
    return {
        "turns": len(stats),
        "completed": completed,
        "failed": failed,
        "partial": sum(1 for stat in stats if stat["partial"]),
        "failure_rate": round(failed / len(stats), 4) if stats else None,
        "error_codes": dict(error_counter),
        "intent_distribution": dict(intent_counter),
        "tool_calls": tool_calls,
        "tool_failures": tool_failures,
        "tool_failure_rate": (
            round(tool_failures / tool_calls, 4) if tool_calls else None
        ),
        "empty_retrievals": empty_retrievals,
        "empty_retrieval_rate": (
            round(empty_retrievals / turns_with_retrieval, 4)
            if turns_with_retrieval
            else None
        ),
        "latency_p50_seconds": percentile(durations, 0.50),
        "latency_p95_seconds": percentile(durations, 0.95),
        "total_tokens": sum(stat["total_tokens"] for stat in stats),
    }


async def load_recent_turns(database_path: Path, hours: float) -> list[list[dict[str, Any]]]:
    """从持久化消息表读时间窗内的回合事件流,按 turn_id 分组。"""

    from teachx.storage.database import Database

    cutoff = time.time() - hours * 3600 if hours > 0 else 0.0
    database = Database(database_path)
    async with database.connect() as connection:
        cursor = await connection.execute(
            "SELECT events, created_at FROM messages"
            " WHERE role = 'assistant' AND events != '[]' AND events IS NOT NULL"
            " AND created_at >= ? ORDER BY created_at",
            (cutoff,),
        )
        rows = await cursor.fetchall()

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        try:
            events = json.loads(row["events"])
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, dict):
                continue
            turn_id = str(event.get("turn_id") or "")
            if turn_id:
                grouped.setdefault(turn_id, []).append(event)
    return [
        grouped[key]
        for key in sorted(
            grouped,
            key=lambda turn_id: min(
                float(event.get("timestamp") or 0)
                for event in grouped[turn_id]
            ),
        )
    ]


def render_report(report: dict[str, Any], *, hours: float) -> str:
    lines = [
        f"在线监控  时间窗: {'全部' if hours <= 0 else f'{hours:g} 小时'}"
        f"  回合数: {report['turns']}"
    ]
    if report["turns"] == 0:
        lines.append("  (时间窗内没有回合数据)")
        return "\n".join(lines)
    lines.append(
        f"  完成 {report['completed']}  失败 {report['failed']}"
        f"  部分回答 {report['partial']}"
        f"  失败率 {_fmt(report['failure_rate'], pct=True)}"
    )
    if report["error_codes"]:
        codes = ", ".join(
            f"{code}×{count}" for code, count in report["error_codes"].items()
        )
        lines.append(f"  错误码: {codes}")
    lines.append(
        f"  工具调用 {report['tool_calls']}  工具失败率 "
        f"{_fmt(report['tool_failure_rate'], pct=True)}"
        f"  空检索率 {_fmt(report['empty_retrieval_rate'], pct=True)}"
    )
    lines.append(
        f"  时延 P50 {_fmt(report['latency_p50_seconds'], suffix='s')}"
        f"  P95 {_fmt(report['latency_p95_seconds'], suffix='s')}"
        f"  token 合计 {report['total_tokens']}"
    )
    if report["intent_distribution"]:
        intents = ", ".join(
            f"{_INTENT_NAMES.get(intent, intent)}×{count}"
            for intent, count in report["intent_distribution"].items()
        )
        lines.append(f"  意图分布: {intents}")
    return "\n".join(lines)


def _fmt(value: Any, *, pct: bool = False, suffix: str = "") -> str:
    if value is None:
        return "—"
    if pct:
        return f"{value * 100:.1f}%"
    if suffix:
        return f"{value:g}{suffix}"
    return f"{value:g}"


async def _run(args: argparse.Namespace) -> int:
    database_path = args.db
    if database_path is None:
        from teachx.config import get_settings

        database_path = get_settings().resolved_database_path()
    turns = await load_recent_turns(database_path, args.hours)
    report = aggregate_turns(turns)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_report(report, hours=args.hours))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="在线监控聚合(事件流 → 指标)")
    parser.add_argument("--db", type=Path, default=None, help="数据库路径,默认环境配置")
    parser.add_argument(
        "--hours", type=float, default=24.0, help="时间窗(小时),0 表示全部"
    )
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = parser.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
