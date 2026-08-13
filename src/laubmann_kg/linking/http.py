"""Minimal stdlib HTTP-GET-JSON helper shared by the linking clients."""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

USER_AGENT = "laubmann-kg-linking/1.0 (HistOrniGraph; totomail.tp@gmail.com)"


def get_json(url: str, params: dict, timeout: float = 30.0) -> Optional[object]:
    """GET ``url`` with urlencoded ``params`` and the UA header. Any
    URLError/HTTPError/timeout/JSONDecodeError -> log warning, return None
    (callers never cache None -> automatic retry next run)."""
    request = urllib.request.Request(
        url + "?" + urllib.parse.urlencode(params),
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except Exception as exc:  # noqa: BLE001 - a failed lookup must never abort the run
        logger.warning("GET %s failed: %s", url, exc)
        return None
