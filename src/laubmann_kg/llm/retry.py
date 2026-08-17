"""Deterministic retry helper for LLM calls."""

from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry_call(
    func: Callable[[], T],
    *,
    attempts: int = 3,
    backoff: float = 0.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    no_retry: tuple[type[BaseException], ...] = (),
) -> T:
    """Call ``func`` up to ``attempts`` times. ``backoff`` defaults to 0 so tests
    run without sleeping; set > 0 for exponential backoff in production.
    ``no_retry`` lists exception types that propagate immediately even when
    they are subclasses of ``exceptions`` (e.g. a truncated-but-valid answer
    that a retry cannot improve)."""
    last: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except no_retry:
            raise
        except exceptions as exc:  # noqa: BLE001 - deliberately broad, re-raised below
            last = exc
            logger.warning("attempt %d/%d failed: %s", attempt, attempts, exc)
            if attempt < attempts and backoff > 0:
                time.sleep(backoff * (2 ** (attempt - 1)))
    assert last is not None
    raise last
