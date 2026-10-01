from __future__ import annotations

from dataclasses import dataclass

from teachx.config import Settings
from teachx.knowledge.service import KnowledgeService
from teachx.providers.base import BaseProvider
from teachx.runtime.engine import AgentRuntime
from teachx.runtime.tools import ToolRegistry
from teachx.storage.repository import SessionRepository


@dataclass(slots=True)
class ApplicationContainer:
    settings: Settings
    repository: SessionRepository
    knowledge: KnowledgeService
    provider: BaseProvider
    tools: ToolRegistry
    runtime: AgentRuntime
