"""检索评测的标准指标。

三个指标分工:
- Hit@K   前 K 条里"有没有"答案 —— 最基本的及格线
- Recall@K 前 K 条里"找全了没有" —— 答案可能分布在多个片段
- MRR     第一条正确答案排多前 —— 排序质量的连续度量

入参统一为:retrieved 是按相关性排好的片段 id 列表,relevant 是标准答案
片段 id 的集合。
"""

from __future__ import annotations


def hit_at_k(retrieved: list[int], relevant: set[int], k: int) -> float:
    """前 K 条中只要出现一条相关结果即为 1.0,否则 0.0。"""
    return 1.0 if set(retrieved[:k]) & relevant else 0.0


def recall_at_k(retrieved: list[int], relevant: set[int], k: int) -> float:
    """前 K 条命中的相关结果占全部相关结果的比例。"""
    if not relevant:
        return 0.0
    return len(set(retrieved[:k]) & relevant) / len(relevant)


def reciprocal_rank(retrieved: list[int], relevant: set[int]) -> float:
    """第一条相关结果的排名的倒数;全未命中为 0.0。"""
    for rank, chunk_id in enumerate(retrieved, start=1):
        if chunk_id in relevant:
            return 1.0 / rank
    return 0.0


def mean(values: list[float]) -> float:
    """所有查询的平均分;空列表为 0.0。"""
    return sum(values) / len(values) if values else 0.0
