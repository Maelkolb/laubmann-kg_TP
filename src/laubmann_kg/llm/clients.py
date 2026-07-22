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


def _build_provider(backend: str, config: dict) -> LLMClient:  # pragma: no cover - needs creds/network
    if backend in ("google", "gemini"):
        return GeminiClient(
            model=config.get("model", "gemini-1.5-flash"),
            api_key_env=config.get("api_key_env", "GOOGLE_API_KEY"),
            temperature=float(config.get("temperature", 0.0)),
        )
    raise NotImplementedError(
        f"LLM backend '{backend}' is not configured. Supported: offline, google/gemini. "
        "Add an adapter or use backend=offline."
    )


class GeminiClient:  # pragma: no cover - needs credentials + network
    """Google Gemini adapter. Lazy-imports the SDK (new ``google-genai`` first,
    then legacy ``google-generativeai``) and forces JSON output at temperature 0
    for deterministic, cacheable extraction."""

    def __init__(self, model: str, api_key_env: str = "GOOGLE_API_KEY",
                 temperature: float = 0.0) -> None:
        self.model = model
        self._api_key_env = api_key_env
        self._temperature = temperature
        self._impl: Optional[tuple[str, object]] = None

    def _ensure(self) -> None:
        if self._impl is not None:
            return
        import os

        key = os.environ.get(self._api_key_env) or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError(
                f"No API key found. Set {self._api_key_env} (or GEMINI_API_KEY) "
                "to use the Gemini extraction backend."
            )
        try:
            from google import genai  # new unified SDK

            self._impl = ("genai", genai.Client(api_key=key))
        except ImportError:
            import google.generativeai as gga  # legacy SDK

            gga.configure(api_key=key)
            self._impl = ("legacy", gga.GenerativeModel(self.model))

    def complete(self, prompt: str) -> str:
        self._ensure()
        kind, obj = self._impl  # type: ignore[misc]
        if kind == "genai":
            from google.genai import types

            resp = obj.models.generate_content(  # type: ignore[attr-defined]
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=self._temperature,
                    response_mime_type="application/json",
                ),
            )
            return resp.text
        resp = obj.generate_content(  # type: ignore[attr-defined]
            prompt,
            generation_config={"temperature": self._temperature,
                               "response_mime_type": "application/json"},
        )
        return resp.text
