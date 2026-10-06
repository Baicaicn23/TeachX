"""端到端 Agent 评测的 LLM-as-a-Judge(学习版,P1,仅手动)。

任务级断言(run_agent_eval)只能检查"结构对不对":调没调工具、路由对不对、
关键词在不在。回答是否**忠实于检索内容、对学习者真的有用**,需要模型来评。
本脚本用真实模型把任务集小样本跑一遍,再让同一个模型按评分细则打分
(忠实度 / 有用性,1~5 分),输出报告供人工留存。

它**不进 CI**:每次运行消耗真实 API 额度,且模型输出不可复现,不能当回归
门禁。运行前需要配置真实 Provider(backend/.env 或环境变量),并显式传
--yes 确认消费:

    # 默认前 5 个任务
    cd backend && uv run python -m teachx.evals.run_agent_judge --yes

    # 指定任务数(上限 20)与数据集
    uv run python -m teachx.evals.run_agent_judge --yes --limit 10

    # 只看计划不执行
    uv run python -m teachx.evals.run_agent_judge
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from teachx.config import get_settings
from teachx.evals.run_agent_eval import DEFAULT_DATASET, load_dataset
from teachx.knowledge.service import KnowledgeService
from teachx.providers import build_provider
from teachx.providers.base import BaseProvider
from teachx.runtime.engine import AgentRuntime
from teachx.runtime.tools import build_default_registry
from teachx.schemas import StartTurnCommand
from teachx.storage.database import Database
from teachx.storage.repository import SessionRepository

MAX_TASKS = 20
DEFAULT_REPORT_DIR = Path(__file__).resolve().parents[3] / "evals" / "reports"

_JUDGE_SYSTEM_PROMPT = """你是严格的教学 AI 助手评审。依据评分细则对一次助手回答打分:

忠实度(faithfulness):回答是否基于给出的参考资料和明确的常识,没有编造
不存在的定义、公式或来源。5=完全基于资料;1=大量编造。
有用性(usefulness):回答是否切中学习者的问题、结构清晰、难度合适。
5=直接解决困惑;1=答非所问。

只输出一行 JSON,不要输出任何其他文字:
{"faithfulness": 1到5的整数, "usefulness": 1到5的整数, "reason": "一句话理由"}"""


@dataclass
class JudgeScore:
    faithfulness: int
    usefulness: int
    reason: str


def parse_judge_json(content: str) -> JudgeScore | None:
    """解析评审 JSON;格式或取值非法时返回 None,不猜测。"""

    text = str(content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    try:
        faithfulness = int(payload["faithfulness"])
        usefulness = int(payload["usefulness"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (1 <= faithfulness <= 5 and 1 <= usefulness <= 5):
        return None
    reason = " ".join(str(payload.get("reason", "")).split())[:200]
    return JudgeScore(faithfulness, usefulness, reason)


def ensure_real_provider(provider: BaseProvider) -> None:
    """Judge 拒绝在 Mock 上运行:评审 Mock 的固定文本没有任何信息量。"""

    if getattr(provider, "name", "") == "mock":
        raise SystemExit(
            "当前 Provider 是 mock,Judge 需要真实模型。请配置 "
            "TEACHX_LLM_PROVIDER=openai 与 API Key 后重试。"
        )


async def run_turn_answer(
    task: dict[str, Any],
    dataset: dict[str, Any],
    provider: BaseProvider,
) -> dict[str, Any]:
    """用真实 Provider 跑一个任务,返回回答与来源摘要。"""

    with tempfile.TemporaryDirectory(prefix="teachx-agent-judge-") as tmp:
        root = Path(tmp)
        database = Database(root / "judge.db")
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
            provider=provider,
            tools=build_default_registry(knowledge),
            repository=SessionRepository(database),
        )
        command = StartTurnCommand(
            type="start_turn",
            content=str(task["input"]),
            knowledge_bases=list(task.get("knowledge_bases") or []),
        )
        events = [event async for event in runtime.run_turn(command)]

    answer = next(
        (str(event.get("content") or "") for event in events if event.get("type") == "result"),
        "",
    )
    sources = []
    for event in events:
        if event.get("type") == "sources":
            for source in event.get("metadata", {}).get("sources") or []:
                sources.append(
                    {
                        "title": source.get("title"),
                        "snippet": " ".join(str(source.get("snippet") or "").split())[:200],
                    }
                )
    intent = next(
        (
            str(event.get("metadata", {}).get("intent"))
            for event in reversed(events)
            if event.get("type") == "done"
        ),
        "",
    )
    return {"answer": answer, "sources": sources, "intent": intent}


async def judge_answer(
    provider: BaseProvider,
    task_input: str,
    answer: str,
    sources: list[dict[str, Any]],
) -> JudgeScore | None:
    """让评审模型按细则给一次回答打分。"""

    source_text = (
        "\n".join(
            f"- [{source['title']}] {source['snippet']}" for source in sources[:5]
        )
        if sources
        else "(本轮没有检索到资料)"
    )
    result = await provider.complete(
        [
            {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"学习者的问题:{task_input}\n\n"
                    f"参考资料:\n{source_text}\n\n"
                    f"助手回答:\n{answer[:2000]}\n\n请评分。"
                ),
            },
        ],
        [],
        # 推理模型会先消耗大量思考 token 再输出 JSON;给太紧的预算会让
        # 评审本身被截断(P1 真实验证踩过的坑)。
        max_output_tokens=1024,
    )
    return parse_judge_json(result.content)


async def run_judge(
    dataset_path: Path,
    provider: BaseProvider,
    limit: int,
) -> dict[str, Any]:
    dataset = load_dataset(dataset_path)
    tasks = dataset["tasks"][:limit]
    rows: list[dict[str, Any]] = []
    started = time.perf_counter()
    for task in tasks:
        outcome = await run_turn_answer(task, dataset, provider)
        score = await judge_answer(
            provider, str(task["input"]), outcome["answer"], outcome["sources"]
        )
        rows.append(
            {
                "task_id": task["id"],
                "input": task["input"],
                "intent": outcome["intent"],
                "answer_chars": len(outcome["answer"]),
                "sources": len(outcome["sources"]),
                "faithfulness": score.faithfulness if score else None,
                "usefulness": score.usefulness if score else None,
                "reason": score.reason if score else "评审输出解析失败",
            }
        )
    scored = [row for row in rows if row["faithfulness"] is not None]
    return {
        "dataset": dataset.get("name"),
        "provider": provider.name,
        "model": str(getattr(provider, "model", provider.name)),
        "tasks": len(rows),
        "parsed": len(scored),
        "mean_faithfulness": (
            sum(row["faithfulness"] for row in scored) / len(scored) if scored else None
        ),
        "mean_usefulness": (
            sum(row["usefulness"] for row in scored) / len(scored) if scored else None
        ),
        "duration_seconds": round(time.perf_counter() - started, 1),
        "rows": rows,
    }


def print_report(report: dict[str, Any]) -> None:
    print(
        f"Provider: {report['provider']}({report['model']})  "
        f"任务: {report['tasks']}  解析成功: {report['parsed']}  "
        f"耗时: {report['duration_seconds']}s"
    )
    for row in report["rows"]:
        print(
            f"  {row['task_id']}  忠实度 {row['faithfulness']}  "
            f"有用性 {row['usefulness']}  来源 {row['sources']}  {row['reason']}"
        )
    if report["mean_faithfulness"] is not None:
        print(
            f"平均忠实度 {report['mean_faithfulness']:.2f}  "
            f"平均有用性 {report['mean_usefulness']:.2f}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="端到端 Agent 评测的 LLM-as-a-Judge(手动)")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--limit", type=int, default=5, help=f"任务数,1~{MAX_TASKS}")
    parser.add_argument(
        "--yes", action="store_true", help="确认消耗真实 API 额度;不传只打印执行计划"
    )
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args(argv)

    limit = max(1, min(MAX_TASKS, args.limit))
    dataset = load_dataset(args.dataset)
    provider = build_provider(get_settings())
    ensure_real_provider(provider)

    planned = dataset["tasks"][:limit]
    print(f"数据集: {dataset.get('name')}  计划任务: {len(planned)}  Provider: {provider.name}")
    for task in planned:
        print(f"  - {task['id']}: {task['input']}")
    if not args.yes:
        print("预览模式:未消耗任何额度。确认执行请加 --yes。")
        return 0

    report = asyncio.run(run_judge(args.dataset, provider, limit))
    print_report(report)
    args.report_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.report_dir / (
        f"agent_judge-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    )
    payload = {**report, "rows": report["rows"]}
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"报告已保存: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
