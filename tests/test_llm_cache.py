from laubmann_kg.llm.cache import LLMCache, cache_key
from laubmann_kg.llm.clients import CachedClient, OfflineClient, build_client
from laubmann_kg.llm.retry import retry_call


def test_cache_key_is_stable_and_order_independent() -> None:
    assert cache_key("m", {"a": 1, "b": 2}) == cache_key("m", {"b": 2, "a": 1})
    assert cache_key("m", "x") != cache_key("m", "y")


def test_cache_roundtrip(tmp_path) -> None:
    cache = LLMCache(tmp_path)
    key = cache_key("model", "prompt")
    assert cache.get(key) is None
    cache.set(key, {"prompt": "prompt"}, "response")
    assert cache.get(key) == "response"


def test_cached_client_calls_underlying_once(tmp_path) -> None:
    calls = {"n": 0}

    class Counting:
        model = "count"

        def complete(self, prompt: str) -> str:
            calls["n"] += 1
            return "ok"

    client = CachedClient(Counting(), cache=LLMCache(tmp_path))
    assert client.complete("hi") == "ok"
    assert client.complete("hi") == "ok"
    assert calls["n"] == 1


def test_offline_client_is_default_and_network_free() -> None:
    client = build_client({"backend": "offline"})
    assert isinstance(client, OfflineClient)
    assert client.complete("anything") == "[]"


def test_retry_call_succeeds_after_failures() -> None:
    state = {"n": 0}

    def flaky() -> str:
        state["n"] += 1
        if state["n"] < 3:
            raise ValueError("transient")
        return "done"

    assert retry_call(flaky, attempts=3, backoff=0.0) == "done"
