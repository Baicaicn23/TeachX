from pathlib import Path

from fastapi.testclient import TestClient

from teachx.config import get_settings
from teachx.main import app


def test_health_and_turn_websocket(tmp_path: Path) -> None:
    settings = get_settings()
    original_database_path = settings.database_path
    original_knowledge_root = settings.knowledge_root
    settings.database_path = tmp_path / "api.db"
    settings.knowledge_root = tmp_path / "knowledge"
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
        settings.knowledge_root = original_knowledge_root


def test_knowledge_upload_and_search(tmp_path: Path) -> None:
    settings = get_settings()
    original_database_path = settings.database_path
    original_knowledge_root = settings.knowledge_root
    settings.database_path = tmp_path / "knowledge-api.db"
    settings.knowledge_root = tmp_path / "knowledge"
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/knowledge-bases",
                data={
                    "name": "课程资料",
                    "rag_provider": "sqlite-fts",
                    "rel_paths": "agent.md",
                },
                files=[
                    (
                        "files",
                        (
                            "agent.md",
                            "Agent Loop 会调用工具并根据结果继续推理。".encode(),
                            "text/markdown",
                        ),
                    )
                ],
            )
            assert response.status_code == 200

            bases = client.get("/api/knowledge-bases").json()["knowledge_bases"]
            assert bases[0]["name"] == "课程资料"

            files = client.get("/api/knowledge-bases/课程资料/files").json()["files"]
            assert files[0]["name"] == "agent.md"

            results = client.get(
                "/api/knowledge-bases/课程资料/search",
                params={"q": "调用工具"},
            ).json()["results"]
            assert results
            assert results[0]["document"] == "agent.md"
    finally:
        settings.database_path = original_database_path
        settings.knowledge_root = original_knowledge_root
