"""P1 端到端任务级评测的门禁测试(全程 Mock,零 API 消耗)。

跑真实 AgentRuntime + Mock 模型的全链路任务考卷(回归门禁),并覆盖
评测集校验、断言失败路径和 Judge 的解析/守卫逻辑(评审脚本本身仅手动)。
"""

import json
from pathlib import Path

import pytest

from teachx.evals.run_agent_eval import (
    DEFAULT_DATASET,
    evaluate_task,
    load_dataset,
    run_eval,
)
from teachx.evals.run_agent_judge import ensure_real_provider, parse_judge_json
from teachx.providers.mock import MockProvider

EXPECTED_TASK_COUNT = 7


def test_agent_task_eval_all_tasks_pass() -> None:
    """回归门禁:任务级考卷必须全绿(与 check.sh 同一份数据集)。"""

    report = run_eval_sync()
    assert report["total"] >= EXPECTED_TASK_COUNT
    assert report["failed"] == 0, [
        (result.task_id, result.failures)
        for result in report["results"]
        if not result.passed
    ]


def run_eval_sync() -> dict:
    return __import__("asyncio").run(run_eval(DEFAULT_DATASET))


def test_agent_task_dataset_rejects_unknown_expect_field(tmp_path: Path) -> None:
    data = {
        "tasks": [
            {
                "id": "t1",
                "input": "随便",
                "expect": {"not_a_real_field": "x"},
            }
        ]
    }
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="未知字段"):
        load_dataset(path)


def test_agent_task_assertions_catch_routing_and_content() -> None:
    """直接对事件流断言:路由错误和内容缺失都必须被抓到(失败路径自证)。"""

    events = [
        {
            "type": "done",
            "metadata": {"status": "completed", "intent": "smalltalk", "agent": "chat"},
        },
        {"type": "content", "content": "你好呀"},
    ]
    task = {
        "id": "t1",
        "input": "计算 12 * 8",
        "expect": {
            "status": "completed",
            "intent": "calculation",
            "agent": "calculator",
            "must_call_tools": ["calculator"],
            "answer_contains": ["96"],
        },
    }
    failures = evaluate_task(task, events)
    checks = {failure["check"] for failure in failures}
    assert checks == {"intent", "agent", "must_call_tools", "answer_contains"}


def test_agent_task_assertions_flag_forbidden_tool() -> None:
    events = [
        {
            "type": "tool_result",
            "metadata": {"tool": "knowledge_search", "success": True},
        },
        {
            "type": "done",
            "metadata": {"status": "completed", "intent": "practice", "agent": "practice"},
        },
        {"type": "content", "content": "题目"},
    ]
    task = {
        "id": "t2",
        "input": "给我出题",
        "expect": {"forbidden_tools": ["knowledge_search"]},
    }
    failures = evaluate_task(task, events)
    assert any(failure["check"] == "forbidden_tools" for failure in failures)


# ---------------------------------------------------------------------------
# Judge(仅手动执行;这里只测解析与守卫,不调用任何真实模型)
# ---------------------------------------------------------------------------


def test_judge_parses_valid_and_fenced_json() -> None:
    plain = parse_judge_json('{"faithfulness": 4, "usefulness": 5, "reason": "基于资料"}')
    assert plain is not None
    assert (plain.faithfulness, plain.usefulness) == (4, 5)
    fenced = parse_judge_json(
        '```json\n{"faithfulness": 3, "usefulness": 2, "reason": "有编造"}\n```'
    )
    assert fenced is not None
    assert (fenced.faithfulness, fenced.usefulness) == (3, 2)


def test_judge_rejects_invalid_scores_and_garbage() -> None:
    assert parse_judge_json('{"faithfulness": 9, "usefulness": 5, "reason": "x"}') is None
    assert parse_judge_json('{"faithfulness": 4, "reason": "缺 usefulness"}') is None
    assert parse_judge_json("我不会评分") is None
    assert parse_judge_json("") is None


def test_judge_refuses_mock_provider() -> None:
    with pytest.raises(SystemExit, match="mock"):
        ensure_real_provider(MockProvider())
