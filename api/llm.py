"""
api/llm.py
==========
LLM provider abstraction — swap between Gemini, Anthropic, etc. via LLM_PROVIDER env var.

To add a new provider:
  1. Create api/providers/<name>.py implementing expand_query() and synthesize()
  2. Add a case to get_provider() below
  3. Set LLM_PROVIDER=<name> in your .env
"""

from typing import Protocol, runtime_checkable
from api.models import Message


@runtime_checkable
class LLMProvider(Protocol):
    def expand_query(self, query: str) -> list[str]:
        """
        Generate paraphrased query variants for multi-query retrieval.
        Must return a list starting with the original query.
        On failure, should return [query] so the pipeline can still run.
        """
        ...

    def synthesize(
        self,
        query: str,
        chunks: list[dict],
        history: list[Message],
        mode: str,
    ) -> tuple[str, dict | None]:
        """
        Synthesize an answer grounded in retrieved chunks.
        Returns (answer_string, usage_dict_or_None).
        Must never raise — return an error message string on failure.
        """
        ...


def get_provider() -> LLMProvider:
    """Return the configured LLM provider instance."""
    from api.config import config

    provider = config.LLM_PROVIDER.lower()

    if provider == "gemini":
        from api.gemini import GeminiProvider
        return GeminiProvider()

    raise ValueError(
        f"Unknown LLM_PROVIDER '{provider}'. "
        "Supported values: gemini. "
        "Add a new case to api/llm.py to support other providers."
    )
