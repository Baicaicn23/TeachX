from teachx.config import Settings
from teachx.providers.base import BaseProvider
from teachx.providers.mock import MockProvider
from teachx.providers.openai_compat import OpenAICompatibleProvider


def build_provider(settings: Settings) -> BaseProvider:
    if settings.llm_provider.lower() == "openai":
        return OpenAICompatibleProvider(
            model=settings.model,
            api_key=settings.api_key,
            base_url=settings.base_url,
            temperature=settings.temperature,
            max_output_tokens=settings.max_output_tokens,
            include_stream_usage=settings.include_stream_usage,
        )
    return MockProvider()


__all__ = ["BaseProvider", "MockProvider", "OpenAICompatibleProvider", "build_provider"]
