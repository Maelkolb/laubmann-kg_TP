"""Content-hash keyed on-disk cache for LLM calls."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path("data/cache/llm")


def cache_key(*parts: Any) -> str:
    payload = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class LLMCache:
    """Deterministic disk cache. Keys are content hashes so identical requests
    reproduce byte-for-byte across runs.

    Record layout: ``{"request": {...}, "response": <text>}``. The KEY is
    ``cache_key(model, prompt)`` only -- generation parameters (temperature,
    max_output_tokens, thinking_level) are stored inside ``request["params"]``
    for audit but deliberately do not invalidate the cache."""

    def __init__(self, cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def get(self, key: str) -> Optional[Any]:
        path = self._path(key)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))["response"]

    def set(self, key: str, request: Any, response: Any, usage: Optional[dict] = None) -> None:
        record = {"request": request, "response": response}
        if usage:
            record["usage"] = usage
        self._path(key).write_text(json.dumps(record, ensure_ascii=False, indent=2),
                                   encoding="utf-8")

    _ledger_lock = threading.Lock()

    def log_usage(self, key: str, model: str, usage: Optional[dict], truncated: bool = False) -> None:
        """Append one line per LIVE call to ``usage.jsonl`` (token counts as the
        provider reported them). Truncated answers are not cached but were paid
        for, so the ledger - not the cache - is the cost record of a run
        (tools/llm_cost.py sums it)."""
        line = json.dumps({"ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
                           "key": key, "model": model, "truncated": truncated, "usage": usage or {}},
                          ensure_ascii=False)
        with self._ledger_lock, (self.cache_dir / "usage.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def get_or_set(self, key: str, request: Any, producer) -> Any:
        hit = self.get(key)
        if hit is not None:
            logger.debug("llm cache hit %s", key)
            return hit
        response = producer()
        self.set(key, request, response)
        return response
