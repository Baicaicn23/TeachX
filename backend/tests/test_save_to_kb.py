""""沉淀进知识库"工具(save_to_knowledge_base)的单元测试。

学生把聊天里出现的题目/笔记一键存进自己的学科库,期末从库里生成复习
材料。覆盖:正常落库(带日期来源头)、自动建库、缺参失败、跨用户保护。
"""

from pathlib import Path

import pytest

from teachx.knowledge.service import KnowledgeError, KnowledgeService
from teachx.runtime.tools import SaveToKnowledgeBaseTool, ToolContext
from teachx.storage.database import Database


@pytest.mark.asyncio
async def test_save_stores_dated_note_into_users_own_kb(tmp_path: Path) -> None:
    database = Database(tmp_path / "save.db")
    await database.initialize()
    service = KnowledgeService(database, tmp_path / "knowledge")
    tool = SaveToKnowledgeBaseTool(service)
    context = ToolContext(user_id="u1", session_id="s1")

    result = await tool.execute(
        context=context,
        knowledge_base="微积分基础",
        title="作业：极限计算题",
        content="求 lim(x→0) sin(x)/x，并说明为什么可以直接用重要极限。",
    )

    assert result.success
    assert "微积分基础" in result.content
    assert result.metadata["saved"] is True
    # 库不存在时自动创建,文件带日期来源头。
    text = await service.get_document_text("微积分基础", "作业：极限计算题.md", "u1")
    assert text is not None
    assert "沉淀于" in text and "来自对话" in text
    assert "sin(x)/x" in text


@pytest.mark.asyncio
async def test_save_requires_login_and_rejects_missing_fields(tmp_path: Path) -> None:
    database = Database(tmp_path / "auth.db")
    await database.initialize()
    service = KnowledgeService(database, tmp_path / "knowledge")
    tool = SaveToKnowledgeBaseTool(service)

    with pytest.raises(Exception, match="登录"):
        await tool.execute(
            context=ToolContext(user_id=""),
            knowledge_base="库",
            title="标题",
            content="内容",
        )
    with pytest.raises(Exception, match="必填"):
        await tool.execute(
            context=ToolContext(user_id="u1"),
            knowledge_base="库",
            title="",
            content="内容",
        )


@pytest.mark.asyncio
async def test_save_cannot_write_into_another_users_kb(tmp_path: Path) -> None:
    database = Database(tmp_path / "cross.db")
    await database.initialize()
    service = KnowledgeService(database, tmp_path / "knowledge")
    await service.create_base("我的线代库", owner_id="u2")  # 别人的库
    tool = SaveToKnowledgeBaseTool(service)

    with pytest.raises(KnowledgeError, match="已存在"):
        await tool.execute(
            context=ToolContext(user_id="u1"),
            knowledge_base="我的线代库",
            title="偷渡",
            content="不该写进别人的库",
        )


@pytest.mark.asyncio
async def test_admin_can_save_into_global_kb(tmp_path: Path) -> None:
    """管理员往全局库(owner_id 为空)沉淀必须成功——这是演示配置的实际路径。

    回归:2026-10-08 端到端测试发现工具漏传 is_admin,导致 ensure_base 的
    "他人同名库"守卫连管理员一起拦下(报"知识库已存在"),沉淀 100% 失败。
    种子数据里五个学科库的 owner_id 全是空、演示账号是首个注册用户(管理员),
    所以这条路径必坏。上一条测试守的是安全语义,本条守的是可用性语义。
    """

    database = Database(tmp_path / "global.db")
    await database.initialize()
    service = KnowledgeService(database, tmp_path / "knowledge")
    await service.create_base("高等数学-微积分", owner_id="")  # 全局库
    tool = SaveToKnowledgeBaseTool(service)

    result = await tool.execute(
        context=ToolContext(user_id="admin1", is_admin=True),
        knowledge_base="高等数学-微积分",
        title="作业：定积分",
        content="求 ∫₀²(3x²+2x)dx。",
    )

    assert result.success
    assert result.metadata["saved"] is True
    text = await service.get_document_text(
        "高等数学-微积分", "作业：定积分.md", "admin1", is_admin=True
    )
    assert text is not None
    assert "3x²+2x" in text


@pytest.mark.asyncio
async def test_non_admin_cannot_write_into_global_kb(tmp_path: Path) -> None:
    """修 is_admin 不能把守卫修掉:普通用户往全局库沉淀仍应被拒。

    与上一条互为边界——同一个 ensure_base 守卫,对管理员放行、对普通用户拦截。
    """

    database = Database(tmp_path / "guard.db")
    await database.initialize()
    service = KnowledgeService(database, tmp_path / "knowledge")
    await service.create_base("高等数学-微积分", owner_id="")  # 全局库
    tool = SaveToKnowledgeBaseTool(service)

    with pytest.raises(KnowledgeError, match="已存在"):
        await tool.execute(
            context=ToolContext(user_id="student1", is_admin=False),
            knowledge_base="高等数学-微积分",
            title="闯入",
            content="普通用户不该写进全局库",
        )
