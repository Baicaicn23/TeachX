"""跨会话长期记忆(学习版,P3)。

会话内的前情提要(教程 24)解决"本轮上下文装不下";学习档案解决"用户是
谁";这里补第三块:**跨会话记住关于用户的长期事实**(在准备考研、偏好
例子先行、正在学线性代数),下会话注入系统提示词,让新对话有一个"记得
你"的起点。

学习版的抽取是**规则化的纯函数**:显式指令("记住:...")与自我陈述
("我是...""我在准备...""我的目标是...")两类模式,零 API 消耗、
确定性可测试;LLM 抽取是文档化的升级路径(接口不变,换实现)。

边界即设计:记忆按 user_id 隔离,内容去重(UNIQUE),注入时标记为
"数据而非指令"(与学习档案同一防注入纪律),可列举、可删除。单用户模式
(认证关闭)没有真实 user_id,统一落到保留作用域 "local"——本地默认体验
同样享受记忆。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from teachx.storage.database import Database

# 认证关闭时的保留记忆作用域。
LOCAL_MEMORY_SCOPE = "local"


def memory_scope(user_id: str) -> str:
    """空 user_id(单用户模式)映射到保留作用域,其余原样返回。"""

    return str(user_id or "").strip() or LOCAL_MEMORY_SCOPE

# 单条记忆的最长字符数;超出截断,避免把整段话当事实存储。
MAX_MEMORY_CHARS = 80
# 注入提示词的最大条数(最近的优先)。
MAX_INJECTION_ITEMS = 10

# 规则抽取:(模式, 捕获组 → 事实前缀)。全部锚定"自我陈述/显式指令"。
_EXTRACT_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"^记住[:：,，\s](.+)$", "{}"),
    (r"^我是(.{2,40}?)(?:[。,,；;!\?\s]|$)", "学习者自称：{}"),
    (r"^我叫(.{1,20}?)(?:[。,,；;!\?\s]|$)", "学习者称呼：{}"),
    (r"^我在(准备|学|复习|刷)(.{1,30}?)(?:[。,,；;!\?\s]|$)", "学习者正在{}{}"),
    (r"^我的(?:学习)?目标是(.{2,40}?)(?:[。,,；;!\?\s]|$)", "学习目标：{}"),
    (r"^我喜欢(.{1,30}?)(?:的(?:讲解|方式|风格))?(?:[。,,；;!\?\s]|$)", "偏好：{}"),
)


@dataclass(frozen=True)
class MemoryItem:
    id: int
    user_id: str
    content: str
    source_session_id: str
    created_at: float
    subject: str = ""


def extract_facts(user_message: str) -> list[str]:
    """从一条用户消息抽取候选长期事实(纯函数,确定性)。

    返回去重、清洗后的事实文本列表;不命中任何模式返回空列表。
    这是"规则版抽取"的唯一入口,LLM 版应替换本函数并保持签名。
    """
    text = " ".join(str(user_message or "").split())
    if not text:
        return []
    facts: list[str] = []
    for pattern, template in _EXTRACT_PATTERNS:
        for match in re.finditer(pattern, text):
            fact = template.format(*[g for g in match.groups() if g is not None])
            fact = " ".join(fact.split())
            # 去掉句读结尾(逐字符,strip 的多字符语义在这里恰好正确但改用
            # 显式循环以避免歧义)。
            while fact and fact[-1] in "。,,；; ":
                fact = fact[:-1]
            if len(fact) < 4:
                continue
            fact = fact[:MAX_MEMORY_CHARS]
            if fact not in facts:
                facts.append(fact)
    return facts


class MemoryError(ValueError):
    pass


class MemoryService:
    """长期记忆的存储与查询:按用户隔离、去重、可列举可删除。"""

    def __init__(self, database: Database) -> None:
        self.database = database

    async def remember(
        self,
        user_id: str,
        content: str,
        *,
        source_session_id: str = "",
        subject: str = "",
    ) -> MemoryItem | None:
        """记录一条记忆;内容重复时返回 None(不覆盖原时间戳)。"""

        clean = " ".join(str(content or "").split())[:MAX_MEMORY_CHARS]
        scope = memory_scope(user_id)
        if len(clean) < 4:
            return None
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                "SELECT id FROM user_memories WHERE user_id = ? AND content = ?",
                (scope, clean),
            )
            if await cursor.fetchone():
                return None
            cursor = await connection.execute(
                "INSERT INTO user_memories (user_id, content, source_session_id,"
                " subject, created_at) VALUES (?, ?, ?, ?, ?)",
                (scope, clean, source_session_id, subject, time.time()),
            )
            memory_id = int(cursor.lastrowid)
            await connection.commit()
        return MemoryItem(
            id=memory_id,
            user_id=scope,
            content=clean,
            source_session_id=source_session_id,
            created_at=time.time(),
            subject=subject,
        )

    async def list_memories(
        self,
        user_id: str,
        *,
        limit: int = MAX_INJECTION_ITEMS,
        prefer_subject: str = "",
    ) -> list[MemoryItem]:
        """某用户的记忆;带 prefer_subject 时该学科的记忆排最前。"""

        async with self.database.connect() as connection:
            cursor = await connection.execute(
                "SELECT id, user_id, content, source_session_id, subject, created_at"
                " FROM user_memories WHERE user_id = ?"
                " ORDER BY created_at DESC, id DESC LIMIT 200",
                (memory_scope(user_id),),
            )
            rows = await cursor.fetchall()
        items = [self._item_from_row(row) for row in rows]
        if prefer_subject:
            matched = [i for i in items if i.subject == prefer_subject]
            rest = [i for i in items if i.subject != prefer_subject]
            items = matched + rest
        return items[: max(1, int(limit))]

    async def delete_memory(self, user_id: str, memory_id: int) -> bool:
        """删除一条记忆;只能删自己的,删不到返回 False。"""

        async with self.database.connect() as connection:
            cursor = await connection.execute(
                "DELETE FROM user_memories WHERE user_id = ? AND id = ?",
                (memory_scope(user_id), int(memory_id)),
            )
            await connection.commit()
            return cursor.rowcount > 0

    async def extract_and_remember(
        self,
        user_id: str,
        user_message: str,
        *,
        session_id: str = "",
        subject: str = "",
    ) -> list[str]:
        """抽取 + 存储;返回实际新增的记忆内容。任何失败不抛出。"""

        try:
            stored: list[str] = []
            for fact in extract_facts(user_message):
                item = await self.remember(
                    user_id, fact, source_session_id=session_id, subject=subject
                )
                if item is not None:
                    stored.append(item.content)
            return stored
        except Exception:  # noqa: BLE001 — 记忆失败绝不阻塞回合
            return []

    @staticmethod
    def _item_from_row(row: Any) -> MemoryItem:
        return MemoryItem(
            id=int(row["id"]),
            user_id=str(row["user_id"]),
            content=str(row["content"]),
            source_session_id=str(row["source_session_id"] or ""),
            created_at=float(row["created_at"]),
            subject=str(row["subject"] if "subject" in row.keys() else ""),
        )


__all__ = [
    "LOCAL_MEMORY_SCOPE",
    "MAX_INJECTION_ITEMS",
    "MAX_MEMORY_CHARS",
    "MemoryError",
    "MemoryItem",
    "MemoryService",
    "extract_facts",
]
