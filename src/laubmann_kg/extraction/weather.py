"""Entry-level weather mapping (LLM output -> WeatherReport)."""

from __future__ import annotations

import re
from typing import Optional

from laubmann_kg.kg.model import WeatherReport
from laubmann_kg.normalization import vocabularies as vocab

_NUM_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def _parse_temperature(value, unit: Optional[str] = None) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        v = float(value)
    else:
        m = _NUM_RE.search(str(value).replace("−", "-"))
        if not m:
            return None
        v = float(m.group(0).replace(",", "."))
    # sanity bound per unit (F sits on a different scale); SHACL mirrors the union
    lo, hi = (-76.0, 140.0) if unit == "F" else (-60.0, 60.0)
    return v if lo <= v <= hi else None


def map_weather(raw) -> Optional[WeatherReport]:
    """Tolerant mapper. None/garbage -> None; bare string -> verbatim-only
    report; list -> first element yielding a report; dict without a non-empty
    verbatim -> None (verbatim is primary and mandatory). A unit without a
    value is dropped as meaningless."""
    if isinstance(raw, list):
        return next((r for r in map(map_weather, raw) if r is not None), None)
    if raw is None:
        return None
    if isinstance(raw, str):
        text = raw.strip()
        return WeatherReport(verbatim=text) if text else None
    if not isinstance(raw, dict):
        return None
    verbatim = (str(raw.get("verbatim") or "")).strip()
    if not verbatim:
        return None
    unit = vocab.normalize_temperature_unit(raw.get("temperature_unit"))
    value = _parse_temperature(raw.get("temperature_value"), unit)
    if value is None:
        unit = None
    wind = raw.get("wind")
    return WeatherReport(
        verbatim=verbatim, temperature_value=value, temperature_unit=unit,
        precipitation=vocab.normalize_precipitation(raw.get("precipitation")),
        wind=(wind.strip() or None) if isinstance(wind, str) else None,
        sky=vocab.normalize_sky(raw.get("sky")),
    )
