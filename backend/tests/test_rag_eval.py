from __future__ import annotations

from pathlib import Path

import pytest

from teachx.evals.metrics import (
    hit_at_k,
    mean,
    recall_at_k,
    reciprocal_rank,
)
from teachx.evals.run_rag_eval import (
    DEFAULT_DATASET,
    compare_with_baseline,
    load_dataset,
    run_eval,
)

# retrieved = [10, 11, 12, 13],相关片段 = {11, 13}
RETRIEVED = [10, 11, 12, 13]
RELEVANT = {11, 13}


def test_hit_at_k() -> None:
    assert hit_at_k(RETRIEVED, RELEVANT, k=1) == 0.0  # 第一条不相关
    assert hit_at_k(RETRIEVED, RELEVANT, k=2) == 1.0  # 第二条命中
    assert hit_at_k([], RELEVANT, k=5) == 0.0


def test_recall_at_k() -> None:
    # 前 2 条里只有 {11},占 2 个相关片段的一半。
    assert recall_at_k(RETRIEVED, RELEVANT, k=2) == 0.5
    # 前 4 条包含 {11, 13},全部找齐。
    assert recall_at_k(RETRIEVED, RELEVANT, k=4) == 1.0
    # 没有标准答案时返回 0,避免除零。
    assert recall_at_k(RETRIEVED, set(), k=4) == 0.0


def test_reciprocal_rank() -> None:
    # 第一条相关结果排在第 2 位 → 1/2。
    assert reciprocal_rank(RETRIEVED, RELEVANT) == 0.5
    assert reciprocal_rank([99, 98], RELEVANT) == 0.0
    assert reciprocal_rank([11, 10], RELEVANT) == 1.0


def test_mean() -> None:
    assert mean([1.0, 0.5, 0.0]) == pytest.approx(0.5)
    assert mean([]) == 0.0


def test_dataset_is_valid_and_self_consistent() -> None:
    dataset = load_dataset(DEFAULT_DATASET)

    assert len(dataset["documents"]) >= 3
    assert len(dataset["queries"]) >= 5
    corpus = "\n".join(doc["content"] for doc in dataset["documents"])
    for item in dataset["queries"]:
        # 每条 gold 关键句必须真的出现在语料里,否则评测永远无法命中。
        assert item["gold"] in corpus, f"gold 不在语料中: {item['gold']}"


@pytest.mark.asyncio
async def test_end_to_end_eval_meets_floor() -> None:
    """端到端跑真实检索管线,分数不得低于回归底线。

    底线留了余量(基线:hit@3=1.0, mrr=0.688):检索单元被改坏时这里会红,
    正常波动不会误报。
    """

    report = await run_eval(DEFAULT_DATASET)

    assert report["query_count"] == len(load_dataset(DEFAULT_DATASET)["queries"])
    assert report["aggregate"]["hit@3"] >= 0.9
    assert report["aggregate"]["recall@3"] >= 0.9
    assert report["aggregate"]["mrr"] >= 0.6


def test_baseline_comparison_detects_regression(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        '{"aggregate": {"hit@3": 1.0, "mrr": 0.688}}', encoding="utf-8"
    )

    good = {"aggregate": {"hit@3": 1.0, "mrr": 0.688}}
    assert compare_with_baseline(good, baseline) == []

    # 下降 0.3,超过 0.05 容差 → 检出退化。
    bad = {"aggregate": {"hit@3": 0.7, "mrr": 0.688}}
    regressions = compare_with_baseline(bad, baseline)
    assert len(regressions) == 1
    assert "hit@3" in regressions[0]

    # 下降 0.03,在容差内 → 不算退化。
    tolerated = {"aggregate": {"hit@3": 0.97, "mrr": 0.688}}
    assert compare_with_baseline(tolerated, baseline) == []
