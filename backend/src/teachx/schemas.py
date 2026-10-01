from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SessionPreferences(BaseModel):
    capability: str | None = "chat"
    tools: list[str] = Field(default_factory=list)
    knowledge_bases: list[str] = Field(default_factory=list)
    language: str = "zh"
    reply_language_override: str | None = None
    selected_branches: dict[str, int] = Field(default_factory=dict)
    pinned: bool = False
    archived: bool = False


class SessionSummary(BaseModel):
    id: str
    session_id: str
    title: str
    created_at: float
    updated_at: float
    message_count: int = 0
    last_message: str = ""
    status: str = "idle"
    active_turn_id: str = ""
    preferences: SessionPreferences = Field(default_factory=SessionPreferences)


class SessionMessage(BaseModel):
    id: int
    session_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    capability: str = ""
    events: list[dict[str, Any]] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: float
    parent_message_id: int | None = None


class SessionDetail(SessionSummary):
    messages: list[SessionMessage] = Field(default_factory=list)
    active_turns: list[dict[str, Any]] = Field(default_factory=list)
    compressed_summary: str = ""
    summary_up_to_msg_id: int | None = None


class SessionList(BaseModel):
    sessions: list[SessionSummary]


class StartTurnCommand(BaseModel):
    type: Literal["start_turn"]
    protocol_version: str = "2.0"
    command_id: str = ""
    client_submission_id: str | None = None
    content: str
    session_id: str | None = None
    capability: str | None = "chat"
    tools: list[str] | None = None
    knowledge_bases: list[str] = Field(default_factory=list)
    language: str | None = None
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


class RenameSessionRequest(BaseModel):
    title: str


class ReplyLanguageRequest(BaseModel):
    language: str | None = None


class OrganizationPatch(BaseModel):
    workspace_id: str | None = None
    course_id: str = ""
    parent_session_id: str = ""
    session_kind: Literal["chat", "selection_tutor"] = "chat"
    pinned: bool | None = None
    archived: bool | None = None


class BranchSelectionRequest(BaseModel):
    selected_branches: dict[str, int] = Field(default_factory=dict)


class QuizResultItem(BaseModel):
    question_id: str = ""
    question: str
    question_type: str = ""
    options: dict[str, str] = Field(default_factory=dict)
    user_answer: str
    correct_answer: str
    explanation: str = ""
    difficulty: str = ""
    is_correct: bool


class QuizResultsRequest(BaseModel):
    answers: list[QuizResultItem] = Field(default_factory=list)
    turn_id: str = ""
