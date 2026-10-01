from __future__ import annotations

from dataclasses import dataclass

from teachx.auth.service import AuthService
from teachx.config import Settings
from teachx.knowledge.service import KnowledgeService
from teachx.practice.service import PracticeService
from teachx.providers.base import BaseProvider
from teachx.runtime.engine import AgentRuntime
from teachx.runtime.tools import ToolRegistry
from teachx.storage.repository import SessionRepository


@dataclass(slots=True)
class ApplicationContainer:
    settings: Settings
    repository: SessionRepository
    auth: AuthService
    knowledge: KnowledgeService
    practice: PracticeService
    provider: BaseProvider
    tools: ToolRegistry
    runtime: AgentRuntime
