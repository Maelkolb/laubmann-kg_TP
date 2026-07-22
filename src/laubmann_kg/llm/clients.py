"""LLM client wrappers with caching, retry, and an offline default.

The default pipeline extraction is rule-based (see extraction/observations.py)
and needs no network. These clients back the optional LLM extraction path and
the test suite, which uses ``OfflineClient`` — a deterministic, network-free
client. Real provider clients are constructed only when explicitly configured
and require credentials.
"""

from __future__ import annotations

import logging
from typing import Optional, Protocol

from laubmann_kg.llm.cache import LLMCache, cache_key
from laubmann_kg.llm.retry import retry_call

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    model: str

    def complete(self, prompt: str) -> str: ...


class OfflineClient:
    """Deterministic, network-free client. Returns a canned response per prompt
    (looked up by content hash); unknown prompts return an empty JSON array,
    i.e. 'no structured output'."""

    def __init__(self, responses: Optional[dict[str, str]] = None, model: str = "offline") -> None:
        self.model = model
        self._responses = responses or {}

    def complete(self, prompt: str) -> str:
        return self._responses.get(cache_key(self.model, prompt), "[]")


class CachedClient:
    """Wraps any client with disk caching and deterministic retry."""

    def __init__(self, client: LLMClient, cache: Optional[LLMCache] = None,
                 attempts: int = 3, backoff: float = 0.0) -> None:
        self.client = client
        self.model = client.model
        self.cache = cache or LLMCache()
        self.attempts = attempts
        self.backoff = backoff

    def complete(self, prompt: str) -> str:
        key = cache_key(self.model, prompt)
        return self.cache.get_or_set(
            key, {"model": self.model, "prompt": prompt},
            lambda: retry_call(lambda: self.client.complete(prompt),
                               attempts=self.attempts, backoff=self.backoff),
        )


def build_client(config: Optional[dict] = None, cache: Optional[LLMCache] = None) -> LLMClient:
    """Build a cached client from config. Defaults to offline/rule-based.

    ``config`` keys: ``backend`` (offline|google|openai|anthropic), ``model``.
    Provider backends lazy-import their SDK and require credentials.
    """
    config = config or {}
    backend = (config.get("backend") or "offline").lower()
    if backend == "offline":
        return OfflineClient(model=config.get("model", "offline"))
    inner = _build_provider(backend, config)
    return CachedClient(inner, cache=cache)


def _build_provider(backend: str, config: dict) -> LLMClient:  # pragma: no cover - needs creds
    raise NotImplementedError(
        f"LLM backend '{backend}' is not configured in this environment. "
        "Set credentials and implement the provider adapter, or use backend=offline."
    )
