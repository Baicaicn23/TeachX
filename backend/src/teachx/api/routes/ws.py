from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from teachx.api.dependencies import get_ws_container
from teachx.auth.models import LOCAL_USER
from teachx.auth.service import InvalidToken
from teachx.schemas import StartTurnCommand

router = APIRouter(tags=["turn-runtime"])


@router.websocket("/ws")
async def unified_turn_socket(websocket: WebSocket) -> None:
    container = get_ws_container(websocket)
    user = LOCAL_USER
    if container.settings.auth_enabled:
        token = websocket.cookies.get(container.settings.auth_cookie_name)
        try:
            authenticated = await container.auth.user_from_token(token)
        except InvalidToken:
            authenticated = None
        if authenticated is None:
            await websocket.close(code=4401, reason="authentication required")
            return
        user = authenticated
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await _send_error(websocket, "invalid_json", "Invalid JSON command")
                continue

            command_type = str(payload.get("type") or "")
            if command_type == "ping":
                await _send(websocket, {"type": "pong"})
                continue
            if command_type == "resume_from":
                await _send(
                    websocket,
                    {
                        "type": "active_turn_info",
                        "turn_id": "",
                        "status": "none",
                        "owner_id": "",
                    },
                )
                continue
            if command_type == "start_turn":
                await _handle_start_turn(
                    websocket,
                    container,
                    payload,
                    user.id,
                    user.is_admin,
                )
                continue
            if command_type in {"cancel_turn", "submit_user_reply", "user_input"}:
                await _send(
                    websocket,
                    {
                        "type": "command_ack",
                        "command_id": str(payload.get("command_id") or ""),
                        "command_type": command_type,
                        "accepted": True,
                        "turn_id": str(payload.get("turn_id") or ""),
                    },
                )
                continue
            await _send_error(
                websocket,
                "unknown_message_type",
                f"Unsupported command type: {command_type}",
            )
    except WebSocketDisconnect:
        return


async def _handle_start_turn(
    websocket: WebSocket,
    container: Any,
    payload: dict[str, Any],
    user_id: str,
    is_admin: bool,
) -> None:
    try:
        command = StartTurnCommand.model_validate(payload)
    except ValidationError as exc:
        await _send_error(
            websocket,
            "invalid_command",
            exc.errors()[0].get("msg", "Invalid start_turn command"),
        )
        return

    sequence = 0
    provider = await container.model_connections.provider_for_user(user_id=user_id)
    async for event in container.runtime.run_turn(
        command,
        user_id=user_id,
        is_admin=is_admin,
        provider=provider,
    ):
        sequence += 1
        event["seq"] = sequence
        event.setdefault("timestamp", time.time())
        await _send(websocket, event)


async def _send_error(websocket: WebSocket, code: str, message: str) -> None:
    await _send(
        websocket,
        {
            "type": "protocol_error",
            "error_code": code,
            "message": message,
            "retryable": False,
        },
    )


async def _send(websocket: WebSocket, payload: dict[str, Any]) -> None:
    await websocket.send_text(
        json.dumps(
            {**payload, "protocol_version": "2.0"},
            ensure_ascii=False,
            default=str,
        )
    )
