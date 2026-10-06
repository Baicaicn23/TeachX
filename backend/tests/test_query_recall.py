"""P2 检索召回优化的单元测试。

覆盖三步改动的行为:同义词查询扩写、FTS trigram 重建迁移(旧库自动升级)、
空结果回退(同 owner 边界内扩大知识库范围 + 如实标记)。
"""

from pathlib import Path

import pytest

from teachx.knowledge.query_rewrite import expand_query, expansion_terms
from teachx.knowledge.service import KnowledgeService
from teachx.runtime.tools import KnowledgeSearchTool, ToolContext
from teachx.storage.database import Database

CORPUS_A = "线性代数课程资料:矩阵的特征值刻画线性变换的缩放因子。"
CORPUS_B = "概率论课程资料:正态分布是连续型概率分布,钟形曲线对称。"


def test_expand_query_appends_domain_synonyms() -> None:
    expanded = expand_query("行列互换后和自己一模一样的矩阵有什么性质")
    assert "转置" in expanded
    assert "对称矩阵" in expanded
    assert expanded.startswith("行列互换后和自己一模一样的矩阵有什么性质")


def test_expand_query_is_noop_without_hits() -> None:
    query = "今天晚饭吃什么"
    assert expand_query(query) == query
    assert expansion_terms(query) == []


def test_expand_query_caps_expansion_terms() -> None:
    # 命中多个模式时术语总数不超过上限,防止过度扩展。
    terms = expansion_terms("方向没变还能装多少内容,求不出逆怎么办")
    assert 0 < len(terms) <= 8


@pytest.mark.asyncio
async def test_trigram_migration_rebuilds_unicode61_index(tmp_path: Path) -> None:
    """旧库(unicode61)在 initialize 时自动重建为 trigram 并重灌数据。"""

    import aiosqlite

    database = Database(tmp_path / "old.db")
    await database.initialize()
    async with aiosqlite.connect(database.path) as connection:
        # 按旧 schema 造一份"存量数据":业务表 + unicode61 索引各一行。
        await connection.execute(
            "INSERT INTO knowledge_bases (name, created_at, updated_at)"
            " VALUES ('kb', 0, 0)"
        )
        await connection.execute(
            "INSERT INTO knowledge_documents (id, kb_name, filename, relative_path,"
            " content, chunk_count, created_at, updated_at)"
            " VALUES (1, 'kb', 'a.md', 'a.md', '正文', 1, 0, 0)"
        )
        await connection.execute(
            "INSERT INTO knowledge_chunks (id, document_id, kb_name, chunk_index,"
            " content, character_count, metadata)"
            " VALUES (1, 1, 'kb', 0, '正态分布是连续型概率分布', 12, '{}')"
        )
        await connection.execute("DROP TABLE knowledge_chunks_fts")
        await connection.execute(
            "CREATE VIRTUAL TABLE knowledge_chunks_fts USING fts5("
            "content, chunk_id UNINDEXED, kb_name UNINDEXED, tokenize='unicode61')"
        )
        await connection.execute(
            "INSERT INTO knowledge_chunks_fts (rowid, content, chunk_id, kb_name)"
            " VALUES (1, '正态分布是连续型概率分布', 1, 'kb')"
        )
        await connection.commit()

    # 直接打开旧库并触发 initialize:应重建索引。
    await database.initialize()

    async with database.connect() as connection:
        cursor = await connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'knowledge_chunks_fts'"
        )
        row = await cursor.fetchone()
        assert "trigram" in str(row["sql"])
        cursor = await connection.execute(
            "SELECT content FROM knowledge_chunks_fts "
            "WHERE knowledge_chunks_fts MATCH '\"正态分布\"'"
        )
        rows = await cursor.fetchall()
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_search_widens_to_other_bases_on_empty(tmp_path: Path) -> None:
    database = Database(tmp_path / "wide.db")
    await database.initialize()
    service = KnowledgeService(database, tmp_path / "knowledge")
    await service.add_document("线代库", "a.md", CORPUS_A.encode(), owner_id="u1")
    await service.add_document("概率库", "b.md", CORPUS_B.encode(), owner_id="u1")

    hits = await service.search(
        "正态分布是什么", ["线代库"], limit=5, owner_id="u1"
    )
    assert hits, "选中库未命中时应扩大到同 owner 的其他知识库"
    assert all(hit.knowledge_base == "概率库" for hit in hits)
    assert all(hit.metadata.get("widened_bases") for hit in hits)


@pytest.mark.asyncio
async def test_search_widening_never_crosses_owner(tmp_path: Path) -> None:
    database = Database(tmp_path / "owner.db")
    await database.initialize()
    service = KnowledgeService(database, tmp_path / "knowledge")
    await service.add_document("线代库", "a.md", CORPUS_A.encode(), owner_id="u1")
    await service.add_document("概率库", "b.md", CORPUS_B.encode(), owner_id="u2")

    hits = await service.search("正态分布", ["线代库"], limit=5, owner_id="u1")
    assert hits == [], "扩大范围只允许同 owner 的知识库,不得越权"


@pytest.mark.asyncio
async def test_tool_tells_the_truth_about_widened_hits(tmp_path: Path) -> None:
    database = Database(tmp_path / "tool.db")
    await database.initialize()
    service = KnowledgeService(database, tmp_path / "knowledge")
    await service.add_document("线代库", "a.md", CORPUS_A.encode(), owner_id="u1")
    await service.add_document("概率库", "b.md", CORPUS_B.encode(), owner_id="u1")
    tool = KnowledgeSearchTool(service)
    context = ToolContext(user_id="u1", knowledge_bases=("线代库",))

    result = await tool.execute(context=context, query="正态分布是什么")

    assert result.success
    assert "自动扩大范围" in result.content
    assert "正态分布" in result.content
