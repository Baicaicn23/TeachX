from __future__ import annotations

import time
from datetime import datetime, timedelta
from datetime import time as datetime_time
from typing import Any, Literal

from teachx.providers.base import LLMUsage
from teachx.storage.database import Database


class UsageService:
    """Persist model usage and evaluate the current user's daily budget."""

    def __init__(self, database: Database) -> None:
        self.database = database

    async def record_call(
        self,
        *,
        user_id: str,
        session_id: str,
        turn_id: str,
        call_kind: str,
        provider: str,
        model: str,
        usage: LLMUsage,
        billable: bool,
    ) -> None:
        identity = _usage_identity(user_id)
        async with self.database.connect() as connection:
            await connection.execute(
                """
                INSERT INTO llm_usage (
                    user_id, session_id, turn_id, call_kind, provider, model,
                    prompt_tokens, completion_tokens, total_tokens,
                    cached_tokens, reasoning_tokens, estimated, billable,
                    duration_seconds, ttft_seconds, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identity,
                    session_id,
                    turn_id,
                    call_kind,
                    provider,
                    model,
                    int(usage.prompt_tokens),
                    int(usage.completion_tokens),
                    int(usage.total_tokens),
                    usage.cached_tokens,
                    usage.reasoning_tokens,
                    int(usage.estimated),
                    int(billable),
                    usage.duration_seconds,
                    usage.ttft_seconds,
                    time.time(),
                ),
            )
            await connection.commit()

    async def daily_status(
        self,
        *,
        user_id: str,
        limit: int,
        exceeded_action: Literal["block", "mock"] = "block",
    ) -> dict[str, Any]:
        used = await self._billable_tokens_today(user_id=user_id)
        enabled = limit > 0
        exceeded = enabled and used >= limit
        return {
            "enabled": enabled,
            "limit_tokens": limit,
            "used_tokens": used,
            "remaining_tokens": max(0, limit - used) if enabled else 0,
            "exceeded": exceeded,
            "exceeded_action": exceeded_action,
        }

    async def _billable_tokens_today(self, *, user_id: str) -> int:
        identity = _usage_identity(user_id)
        start, end = _local_day_bounds()
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                SELECT COALESCE(SUM(total_tokens), 0)
                FROM llm_usage
                WHERE user_id = ? AND billable = 1
                  AND created_at >= ? AND created_at < ?
                """,
                (identity, start, end),
            )
            row = await cursor.fetchone()
        return int(row[0] if row else 0)


def _local_day_bounds(now: datetime | None = None) -> tuple[float, float]:
    current = now or datetime.now().astimezone()
    if current.tzinfo is None:
        current = current.astimezone()
    start = datetime.combine(current.date(), datetime_time.min, tzinfo=current.tzinfo)
    end = start + timedelta(days=1)
    return start.timestamp(), end.timestamp()


def _usage_identity(user_id: str) -> str:
    return user_id or "__local__"
