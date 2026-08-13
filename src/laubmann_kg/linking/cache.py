"""Resumable on-disk JSON cache for the linking API clients."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class JsonCache:
    """Resumable on-disk JSON cache (georef_places.py Nominatim pattern):
    one JSON file, key -> raw JSON-serializable response. Failures (None) are
    never stored, so they retry next run; EMPTY results (GBIF matchType NONE,
    zero Wikidata hits) ARE valid cached answers. Flushes every ``flush_every``
    puts and on flush(); writes are atomic (tmp file + os.replace)."""

    def __init__(self, path: Path, flush_every: int = 25) -> None:
        self.path = Path(path)
        self.flush_every = flush_every
        self._pending = 0
        self._data: dict = {}
        if self.path.exists():
            self._data = json.loads(self.path.read_text(encoding="utf-8"))

    def get(self, key: str):
        """None == miss (None is never stored)."""
        return self._data.get(key)

    def put(self, key: str, value) -> None:
        if value is None:
            return
        self._data[key] = value
        self._pending += 1
        if self._pending >= self.flush_every:
            self.flush()

    def flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)
        self._pending = 0

    def __contains__(self, key: str) -> bool:
        return key in self._data
