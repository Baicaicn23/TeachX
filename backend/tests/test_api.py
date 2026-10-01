from pathlib import Path

from fastapi.testclient import TestClient

from teachx.config import get_settings
from teachx.main import app


def test_health_and_turn_websocket(tmp_path: Path) -> None:
    settings = get_settings()
    original_database_path = settings.database_path
    settings.database_path = tmp_path / "api.db"
    try:
        with TestClient(app) as client:
            assert client.get("/health").json()["status"] == "ok"

            with client.websocket_connect("/ws") as websocket:
                websocket.send_json(
                    {
                        "type": "start_turn",
                        "protocol_version": "2.0",
                        "command_id": "api-test",
                        "content": "计算 6 * 7",
                        "capability": "chat",
                    }
                )
                event_types: list[str] = []
                while True:
                    event = websocket.receive_json()
                    event_types.append(event["type"])
                    if event["type"] == "done":
                        assert event["metadata"]["status"] == "completed"
                        break

            assert event_types[0] == "session"
            assert "tool_call" in event_types
            assert event_types[-1] == "done"
            sessions = client.get("/api/sessions").json()["sessions"]
            assert len(sessions) == 1
    finally:
        settings.database_path = original_database_path
