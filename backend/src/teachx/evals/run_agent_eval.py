"""端到端任务级 Agent 评测(学习版,P1)。

与检索评测(教程 22)评"检索环节"不同,这份考卷评的是**整个回合**:真实
AgentRuntime + Mock 模型从用户输入跑到最终回答,断言路由(意图/子 agent)、
工具行为(必调/禁止/引用条数)和回答内容。全部确定性、零 API 消耗,进
check 门禁。某个任务失败时,自动调 turn_trace 分析器把失败归因到
模型 / 检索 / 工具 / 编排 / 费用五层之一。

用法(在 backend/ 目录下):

    # 跑一次评测,打印每个任务的判定;有失败则附 trace 归因
    uv run python -m teachx.evals.run_agent_eval

    # 与基线对比(退出码 0 = 全部通过)
    uv run python -m teachx.evals.run_agent_eval --quiet

自动测试 tests/test_agent_eval.py 跑同一份考卷作为回归门禁。真实模型的
小样本 LLM-as-a-Judge 见 run_agent_judge(仅手动,不进 CI)。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from teachx.knowledge.service import KnowledgeService
from teachx.providers.mock import MockProvider
from teachx.runtime.engine import AgentRuntime
from teachx.runtime.tools import build_default_registry
from teachx.runtime.turn_trace import analyze_turn_events, render_trace
from teachx.schemas import StartTurnCommand
from teachx.storage.database import Database
from teachx.storage.repository import SessionRepository

DEFAULT_DATASET = (
    Path(__file__).resolve().parents[3] / "evals" / "datasets" / "agent_tasks.json"
)

# 断言字段白名单:评测集写错字段名直接报错,不静默忽略。
EXPECT_KEYS = frozenset(
    {
        "status",
        "intent",
        "intent_detector",
        "agent",
        "must_call_tools",
        "forbidden_tools",
        "answer_contains",
        "answer_not_contains",
        "min_sources",
    }
)


@dataclass
class TaskResult:
    task_id: str
    passed: bool
    failures: list[dict[str, str]] = field(default_factory=list)
    session_id: str = ""
    answer: str = ""
    tools_called: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)


def load_dataset(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("tasks",):
        if key not in data:
            raise ValueError(f"评测集缺少字段: {key}")
    for index, task in enumerate(data["tasks"], start=1):
        if not task.get("id") or not task.get("input"):
            raise ValueError(f"第 {index} 个任务缺少 id 或 input")
        unknown = set(task.get("expect", {})) - EXPECT_KEYS
        if unknown:
            raise ValueError(f"任务 {task['id']} 的 expect 有未知字段: {sorted(unknown)}")
    return data


def _final_answer(events: list[dict[str, Any]]) -> str:
    """从事件流取最终回答:优先 result 事件,否则拼接增量片段。"""

    for event in events:
        if event.get("type") == "result":
            return str(event.get("content") or "")
    return "".join(
        str(event.get("content") or "")
        for event in events
        if event.get("type") == "content"
    )


def _tools_called(events: list[dict[str, Any]]) -> list[str]:
    return [
        str(event["metadata"]["tool"])
        for event in events
        if event.get("type") == "tool_result" and "tool" in event.get("metadata", {})
    ]


def _sources_count(events: list[dict[str, Any]]) -> int:
    counts = [
        len(event["metadata"].get("sources") or [])
        for event in events
        if event.get("type") == "sources"
    ]
    return max(counts) if counts else 0


def evaluate_task(task: dict[str, Any], events: list[dict[str, Any]]) -> list[dict[str, str]]:
    """按 expect 断言检查一个任务的事件流,返回失败清单(空 = 通过)。"""

    expect = task.get("expect", {})
    done = next((event for event in reversed(events) if event.get("type") == "done"), {})
    done_meta = done.get("metadata", {}) if isinstance(done.get("metadata"), dict) else {}
    answer = _final_answer(events)
    tools_called = _tools_called(events)
    sources = _sources_count(events)
    failures: list[dict[str, str]] = []

    def check(name: str, expected: Any, actual: Any) -> None:
        if expected != actual:
            failures.append(
                {
                    "check": name,
                    "expected": json.dumps(expected, ensure_ascii=False),
                    "actual": json.dumps(actual, ensure_ascii=False),
                }
            )

    if "status" in expect:
        check("status", expect["status"], str(done_meta.get("status")))
    if "intent" in expect:
        check("intent", expect["intent"], str(done_meta.get("intent")))
    if "intent_detector" in expect:
        check(
            "intent_detector",
            expect["intent_detector"],
            str(done_meta.get("intent_detector")),
        )
    if "agent" in expect:
        check("agent", expect["agent"], str(done_meta.get("agent")))

    if "must_call_tools" in expect:
        missing = sorted(set(expect["must_call_tools"]) - set(tools_called))
        if missing:
            failures.append(
                {
                    "check": "must_call_tools",
                    "expected": json.dumps(expect["must_call_tools"], ensure_ascii=False),
                    "actual": json.dumps(tools_called, ensure_ascii=False),
                    "detail": f"缺少调用: {missing}",
                }
            )
    if "forbidden_tools" in expect:
        violated = sorted(set(expect["forbidden_tools"]) & set(tools_called))
        if violated:
            failures.append(
                {
                    "check": "forbidden_tools",
                    "expected": f"不得调用 {expect['forbidden_tools']}",
                    "actual": json.dumps(tools_called, ensure_ascii=False),
                    "detail": f"违反最小权限: {violated}",
                }
            )
    if "answer_contains" in expect:
        for fragment in expect["answer_contains"]:
            if fragment not in answer:
                failures.append(
                    {
                        "check": "answer_contains",
                        "expected": f"回答包含 {fragment!r}",
                        "actual": " ".join(answer.split())[:120],
                    }
                )
    if "answer_not_contains" in expect:
        for fragment in expect["answer_not_contains"]:
            if fragment in answer:
                failures.append(
                    {
                        "check": "answer_not_contains",
                        "expected": f"回答不包含 {fragment!r}",
                        "actual": " ".join(answer.split())[:120],
                    }
                )
    if "min_sources" in expect and sources < int(expect["min_sources"]):
        failures.append(
            {
                "check": "min_sources",
                "expected": f">= {expect['min_sources']}",
                "actual": str(sources),
            }
        )
    return failures


async def run_eval(dataset_path: Path) -> dict[str, Any]:
    """临时库 + Mock 模型全链路执行每个任务,输出聚合结果与失败明细。"""

    dataset = load_dataset(dataset_path)
    results: list[TaskResult] = []

    with tempfile.TemporaryDirectory(prefix="teachx-agent-eval-") as tmp:
        root = Path(tmp)
        database = Database(root / "eval.db")
        await database.initialize()
        knowledge = KnowledgeService(database, root / "knowledge")
        for document in dataset.get("documents", []):
            await knowledge.add_document(
                str(dataset["knowledge_base"]),
                str(document["filename"]),
                str(document["content"]).encode("utf-8"),
                owner_id=str(dataset.get("owner_id") or ""),
            )
        runtime = AgentRuntime(
            provider=MockProvider(),
            tools=build_default_registry(knowledge),
            repository=SessionRepository(database),
            intent_llm_enabled=False,  # Mock 短路规则路径;显式关闭避免歧义
        )
        for task in dataset["tasks"]:
            command = StartTurnCommand(
                type="start_turn",
                content=str(task["input"]),
                knowledge_bases=list(task.get("knowledge_bases") or []),
            )
            events = [event async for event in runtime.run_turn(command)]
            session_id = str(events[0].get("session_id") or "") if events else ""
            failures = evaluate_task(task, events)
            results.append(
                TaskResult(
                    task_id=str(task["id"]),
                    passed=not failures,
                    failures=failures,
                    session_id=session_id,
                    answer=_final_answer(events),
                    tools_called=_tools_called(events),
                    events=events,
                )
            )

    passed = sum(1 for result in results if result.passed)
    return {
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": passed / len(results) if results else 0.0,
        "results": results,
    }


def print_report(report: dict[str, Any], *, quiet: bool = False) -> None:
    print(
        f"任务: {report['total']}  通过: {report['passed']}"
        f"  失败: {report['failed']}  通过率: {report['pass_rate']:.3f}"
    )
    for result in report["results"]:
        mark = "✓" if result.passed else "✗"
        tools = ",".join(result.tools_called) or "无工具"
        print(f"  {mark} {result.task_id}  工具[{tools}]")
        if result.passed or quiet:
            continue
        for failure in result.failures:
            detail = f"  ({failure['detail']})" if failure.get("detail") else ""
            print(
                f"    断言 {failure['check']} 失败{detail}:"
                f" 期望 {failure['expected']}  实际 {failure['actual']}"
            )
        # 失败归因:复用回合 trace 分析器,把问题定位到五层之一。
        trace_text = render_trace(analyze_turn_events(result.events))
        print(
            "\n".join(f"    trace | {line}" for line in trace_text.splitlines())
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="端到端任务级 Agent 评测(Mock 全链路)")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--quiet", action="store_true", help="只打印聚合结果")
    args = parser.parse_args(argv)

    report = asyncio.run(run_eval(args.dataset))
    print_report(report, quiet=args.quiet)
    if report["failed"]:
        print(f"评测失败: {report['failed']} 个任务未通过断言。")
        return 1
    print("评测通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
