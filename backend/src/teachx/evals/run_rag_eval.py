"""RAG 检索离线评测(学习版)。

用固定的评测数据集跑真实的检索管线(提取 → 切块 → FTS5 + 向量 → RRF),
输出可复现的指标,并与已保存的基线对比,防止改动让检索质量悄悄退化。

用法(在 backend/ 目录下):

    # 跑一次评测,打印每题得分和聚合指标
    TEACHX_EMBEDDING_PROVIDER=mock uv run python -m teachx.evals.run_rag_eval

    # 把当前分数保存为基线(基线文件提交进 Git,作为回归基准)
    uv run python -m teachx.evals.run_rag_eval --save ../evals/baselines/rag_retrieval.json

    # 与基线对比,任一指标下降超过容差(默认 0.05)则以退出码 1 失败
    uv run python -m teachx.evals.run_rag_eval --baseline ../evals/baselines/rag_retrieval.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from teachx.config import get_settings
from teachx.evals.metrics import hit_at_k, mean, recall_at_k, reciprocal_rank
from teachx.knowledge.embeddings import build_embedding_provider
from teachx.knowledge.service import KnowledgeService
from teachx.storage.database import Database

DEFAULT_DATASET = (
    Path(__file__).resolve().parents[3] / "evals" / "datasets" / "rag_retrieval.json"
)
K_VALUES = (3, 5)
REGRESSION_TOLERANCE = 0.05


def load_dataset(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("documents", "queries", "knowledge_base", "owner_id"):
        if key not in data:
            raise ValueError(f"评测集缺少字段: {key}")
    for index, query in enumerate(data["queries"], start=1):
        if not query.get("query") or not query.get("gold"):
            raise ValueError(f"第 {index} 个查询缺少 query 或 gold 字段")
    return data


async def run_eval(
    dataset_path: Path,
    *,
    k_values: tuple[int, ...] = K_VALUES,
    embedding_provider: str = "mock",
    embedding_model: str | None = None,
    rrf_k: int = 60,
    recall_depth: int = 3,
    expand_synonyms: bool = True,
) -> dict[str, Any]:
    """建临时知识库 → 灌入语料 → 逐题检索 → 计算指标。

    embedding_provider 默认 mock(hash 哑向量,确定性、零消耗);传 "openai"
    时走真实 Embeddings API(需要 OPENAI_API_KEY / OPENAI_BASE_URL 指向支持
    embeddings 的平台),用于 E8 的前后对比。

    P2 扫参入口:rrf_k / recall_depth / expand_synonyms 透传给检索服务,
    供量化对比(见教程 27);默认值即当前选定配置。
    """
    dataset = load_dataset(dataset_path)
    max_k = max(k_values)

    with tempfile.TemporaryDirectory(prefix="teachx-eval-") as tmp:
        knowledge_root = Path(tmp) / "knowledge"
        database = Database(Path(tmp) / "eval.db")
        await database.initialize()
        settings = get_settings()
        embedder = build_embedding_provider(
            provider=embedding_provider,
            model=embedding_model or settings.embedding_model,
            api_key=settings.api_key,
            base_url=settings.base_url,
        )
        if embedding_provider != "mock" and embedder is None:
            raise SystemExit(
                f"embedding provider={embedding_provider} 未构建成功,"
                "请检查 OPENAI_API_KEY / OPENAI_BASE_URL 配置"
            )
        service = KnowledgeService(
            database,
            knowledge_root,
            embedder=embedder,
            recall_depth=recall_depth,
            rrf_k=rrf_k,
            expand_synonyms=expand_synonyms,
        )
        kb = dataset["knowledge_base"]
        owner = dataset["owner_id"]

        for doc in dataset["documents"]:
            await service.add_document(
                kb,
                doc["filename"],
                doc["content"].encode("utf-8"),
                owner_id=owner,
            )

        # 标准答案集:全库中包含 gold 关键句的片段都算相关片段。
        all_chunks = await _all_chunks(database, kb)
        rows: list[dict[str, Any]] = []
        for item in dataset["queries"]:
            gold = item["gold"]
            relevant = {cid for cid, content in all_chunks if gold in content}
            hits = await service.search(
                item["query"], [kb], limit=max_k, owner_id=owner
            )
            retrieved = [hit.chunk_id for hit in hits]
            rows.append(
                {
                    "query": item["query"],
                    "gold": gold,
                    "relevant_count": len(relevant),
                    "retrieved_count": len(retrieved),
                    "hit_at_k": {k: hit_at_k(retrieved, relevant, k) for k in k_values},
                    "recall_at_k": {
                        k: recall_at_k(retrieved, relevant, k) for k in k_values
                    },
                    "reciprocal_rank": reciprocal_rank(retrieved, relevant),
                }
            )

    return {
        "dataset": dataset.get("name", dataset_path.stem),
        "embedding_provider": embedding_provider,
        "embedding_model": embedding_model or "default",
        "params": {
            "rrf_k": rrf_k,
            "recall_depth": recall_depth,
            "expand_synonyms": expand_synonyms,
        },
        "query_count": len(rows),
        "rows": rows,
        "aggregate": {
            **{
                f"hit@{k}": mean([row["hit_at_k"][k] for row in rows])
                for k in k_values
            },
            **{
                f"recall@{k}": mean([row["recall_at_k"][k] for row in rows])
                for k in k_values
            },
            "mrr": mean([row["reciprocal_rank"] for row in rows]),
        },
    }


async def _all_chunks(database: Database, kb: str) -> list[tuple[int, str]]:
    async with database.connect() as connection:
        cursor = await connection.execute(
            "SELECT id, content FROM knowledge_chunks WHERE kb_name = ?",
            (kb,),
        )
        return [(int(row["id"]), str(row["content"])) for row in await cursor.fetchall()]


def print_report(report: dict[str, Any]) -> None:
    print(
        f"评测集: {report['dataset']}  查询数: {report['query_count']}"
        f"  Embedding: {report.get('embedding_provider', 'mock')}"
    )
    print("-" * 72)
    for row in report["rows"]:
        hit = row["hit_at_k"][3]
        print(
            f"{'命中' if hit else '未中'}  RR={row['reciprocal_rank']:.2f}  "
            f"相关片段 {row['relevant_count']} 个  {row['query']}"
        )
    print("-" * 72)
    for key, value in report["aggregate"].items():
        print(f"{key:>10}: {value:.3f}")


def compare_with_baseline(
    report: dict[str, Any],
    baseline_path: Path,
    tolerance: float = REGRESSION_TOLERANCE,
) -> list[str]:
    """返回所有超过容差的退化项描述;空列表表示通过。"""
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    regressions = []
    for key, current in report["aggregate"].items():
        previous = baseline.get("aggregate", {}).get(key)
        if previous is None:
            continue
        if current < previous - tolerance:
            regressions.append(
                f"{key}: {previous:.3f} -> {current:.3f}(下降超过容差 {tolerance})"
            )
    return regressions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TeachX RAG 检索离线评测")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--embedding-provider",
        default="mock",
        help="mock(默认,零消耗)或 openai(真实 Embeddings API)",
    )
    parser.add_argument("--embedding-model", default=None, help="覆盖嵌入模型名")
    parser.add_argument("--save", type=Path, help="把本次结果保存为基线 JSON")
    parser.add_argument("--baseline", type=Path, help="与已保存的基线对比")
    parser.add_argument("--rrf-k", type=int, default=60, help="RRF 融合常数 k(P2 扫参)")
    parser.add_argument(
        "--recall-depth", type=int, default=3, help="每路召回深度倍数(P2 扫参)"
    )
    parser.add_argument(
        "--no-expand", action="store_true", help="关闭同义词查询扩写(P2 A/B)"
    )
    args = parser.parse_args(argv)

    report = asyncio.run(
        run_eval(
            args.dataset,
            embedding_provider=args.embedding_provider,
            embedding_model=args.embedding_model,
            rrf_k=args.rrf_k,
            recall_depth=args.recall_depth,
            expand_synonyms=not args.no_expand,
        )
    )
    print_report(report)

    if args.save:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        args.save.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"已保存基线到 {args.save}")

    if args.baseline:
        regressions = compare_with_baseline(report, args.baseline)
        if regressions:
            print("回归检测:检出退化项", file=sys.stderr)
            for item in regressions:
                print(f"  - {item}", file=sys.stderr)
            return 1
        print("回归检测:与基线相比无退化")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
