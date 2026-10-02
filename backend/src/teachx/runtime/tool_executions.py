from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

from teachx.storage.database import Database

_KEY_SEPARATOR = "\x1f"


def canonical_arguments_json(arguments: dict[str, Any]) -> str:
    """Serialize arguments deterministically so equal payloads hash equally."""
    return json.dumps(
        arguments,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def arguments_hash(arguments: dict[str, Any]) -> str:
    return hashlib.sha256(
        canonical_arguments_json(arguments).encode("utf-8")
    ).hexdigest()


def compute_idempotency_key(
    *,
    user_id: str,
    session_id: str,
    turn_id: str,
    call_id: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    """Derive a stable key for one concrete tool call.

    The key must be stable across retries of the same business request and
    isolated per user, so random UUIDs or a bare ``call_id`` are not enough.
    Only the argument fingerprint is stored, never the raw arguments.
    """
    payload = _KEY_SEPARATOR.join(
        [
            user_id,
            session_id,
            turn_id,
            call_id,
            tool_name,
            arguments_hash(arguments),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(slots=True, frozen=True)
class ToolExecutionRecord:
    """One persisted tool execution keyed by its idempotency key."""

    idempotency_key: str
    user_id: str
    session_id: str
    turn_id: str
    call_id: str
    tool_name: str
    arguments_hash: str
    read_only: bool
    status: str
    result_content: str
    result_metadata: dict[str, Any]
    error_content: str
    attempt_count: int
    created_at: float
    updated_at: float

    @property
    def retryable(self) -> bool:
        return bool(self.result_metadata.get("retryable"))


@dataclass(slots=True, frozen=True)
class ExecutionClaim:
    """Outcome of trying to become the executor for one idempotency key."""

    claimed: bool
    record: ToolExecutionRecord | None


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


class ToolExecutionStore:
    """SQLite-backed ledger that gives tool calls exactly-once side effects.

    The unique primary key plus an atomic ``INSERT OR IGNORE`` is the whole
    concurrency story: for a single SQLite instance, exactly one requester can
    insert the ``running`` row, and everyone else reads that row instead of
    re-executing the tool. No in-memory dict or distributed lock is needed.
    """

    def __init__(
        self,
        database: Database,
        *,
        stale_seconds: float = 300.0,
        in_progress_poll_seconds: float = 0.02,
        in_progress_max_wait_seconds: float = 5.0,
    ) -> None:
        self.database = database
        self.stale_seconds = stale_seconds
        self.in_progress_poll_seconds = in_progress_poll_seconds
        self.in_progress_max_wait_seconds = in_progress_max_wait_seconds

    async def begin(
        self,
        *,
        idempotency_key: str,
        user_id: str,
        session_id: str,
        turn_id: str,
        call_id: str,
        tool_name: str,
        arguments_hash: str,
        read_only: bool,
    ) -> ExecutionClaim:
        """Atomically claim the right to execute one tool call.

        Returns ``claimed=True`` for the first request. Everyone else gets the
        existing record: a ``completed`` or permanent ``failed`` row is replayed,
        a stale ``running`` row or a retryable ``failed`` row is taken over.
        """
        now = time.time()
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                """
                INSERT OR IGNORE INTO tool_executions (
                    idempotency_key, user_id, session_id, turn_id, call_id,
                    tool_name, arguments_hash, read_only, status,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running', ?, ?)
                """,
                (
                    idempotency_key,
                    user_id,
                    session_id,
                    turn_id,
                    call_id,
                    tool_name,
                    arguments_hash,
                    1 if read_only else 0,
                    now,
                    now,
                ),
            )
            await connection.commit()
            if cursor.rowcount == 1:
                return ExecutionClaim(claimed=True, record=None)
            record = await self._read(connection, idempotency_key)

        if record is None:
            # The claim row disappeared between insert and read; let the
            # caller execute directly rather than inventing a fake state.
            return ExecutionClaim(claimed=True, record=None)

        if record.status == "running":
            stale_before = now - self.stale_seconds
            if record.updated_at <= stale_before and await self._take_lease(
                idempotency_key,
                condition="status = 'running' AND updated_at <= ?",
                condition_params=(stale_before,),
            ):
                return ExecutionClaim(claimed=True, record=None)
            return ExecutionClaim(claimed=False, record=record)

        if record.status == "failed" and record.retryable:
            # A transient failure is not a business verdict: a later request
            # may re-execute, but only one requester may win the takeover.
            if await self._take_lease(
                idempotency_key,
                condition="status = 'failed'",
                condition_params=(),
            ):
                return ExecutionClaim(claimed=True, record=None)

        return ExecutionClaim(claimed=False, record=record)

    async def complete(
        self,
        idempotency_key: str,
        *,
        result_content: str,
        result_metadata: dict[str, Any],
        attempt_count: int,
    ) -> None:
        await self._finalize(
            idempotency_key,
            status="completed",
            result_content=result_content,
            result_metadata=result_metadata,
            error_content="",
            attempt_count=attempt_count,
        )

    async def fail(
        self,
        idempotency_key: str,
        *,
        error_content: str,
        result_metadata: dict[str, Any],
        attempt_count: int,
    ) -> None:
        await self._finalize(
            idempotency_key,
            status="failed",
            result_content="",
            result_metadata=result_metadata,
            error_content=error_content,
            attempt_count=attempt_count,
        )

    async def get(self, idempotency_key: str) -> ToolExecutionRecord | None:
        async with self.database.connect() as connection:
            return await self._read(connection, idempotency_key)

    async def wait_for_terminal(self, idempotency_key: str) -> ToolExecutionRecord | None:
        """Poll a ``running`` record briefly; return whatever state it reaches."""
        deadline = time.monotonic() + self.in_progress_max_wait_seconds
        while True:
            record = await self.get(idempotency_key)
            if record is None or record.status != "running":
                return record
            if time.monotonic() >= deadline:
                return record
            await asyncio.sleep(self.in_progress_poll_seconds)

    async def _finalize(
        self,
        idempotency_key: str,
        *,
        status: str,
        result_content: str,
        result_metadata: dict[str, Any],
        error_content: str,
        attempt_count: int,
    ) -> None:
        now = time.time()
        async with self.database.connect() as connection:
            await connection.execute(
                """
                UPDATE tool_executions
                SET status = ?,
                    result_content = ?,
                    result_metadata = ?,
                    error_content = ?,
                    attempt_count = ?,
                    updated_at = ?
                WHERE idempotency_key = ?
                """,
                (
                    status,
                    result_content,
                    json.dumps(result_metadata, ensure_ascii=False, default=str),
                    error_content,
                    attempt_count,
                    now,
                    idempotency_key,
                ),
            )
            await connection.commit()

    async def _take_lease(
        self,
        idempotency_key: str,
        *,
        condition: str,
        condition_params: tuple[Any, ...],
    ) -> bool:
        """Claim an existing row for re-execution if it is still in the expected state."""
        now = time.time()
        async with self.database.connect() as connection:
            cursor = await connection.execute(
                f"""
                UPDATE tool_executions
                SET status = 'running', updated_at = ?
                WHERE idempotency_key = ? AND {condition}
                """,
                (now, idempotency_key, *condition_params),
            )
            await connection.commit()
            return cursor.rowcount == 1

    @staticmethod
    async def _read(
        connection: Any,
        idempotency_key: str,
    ) -> ToolExecutionRecord | None:
        cursor = await connection.execute(
            "SELECT * FROM tool_executions WHERE idempotency_key = ?",
            (idempotency_key,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return ToolExecutionRecord(
            idempotency_key=str(row["idempotency_key"]),
            user_id=str(row["user_id"]),
            session_id=str(row["session_id"]),
            turn_id=str(row["turn_id"]),
            call_id=str(row["call_id"]),
            tool_name=str(row["tool_name"]),
            arguments_hash=str(row["arguments_hash"]),
            read_only=bool(row["read_only"]),
            status=str(row["status"]),
            result_content=str(row["result_content"]),
            result_metadata=_json_loads(row["result_metadata"], {}),
            error_content=str(row["error_content"]),
            attempt_count=int(row["attempt_count"]),
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
        )
