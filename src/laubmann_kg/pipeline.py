"""Corpus → in-memory model pipeline shared by the extraction and export stages.

Loads the frozen corpus interface (entries.csv + multimodal), builds domain
objects, and runs rule-based extraction. Switching from the sample to the
deduped corpus is a path change in the config, not a code change.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from laubmann_kg.extraction.observations import extract_observations
from laubmann_kg.io.csv import read_entries
from laubmann_kg.io.metadata import read_multimodal
from laubmann_kg.kg.model import DiaryEntry, Place
from laubmann_kg.normalization.dates import normalize_date
from laubmann_kg.normalization.places import normalize_place
from laubmann_kg.normalization.taxa import build_resolver

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    entries: list[DiaryEntry] = field(default_factory=list)
    places: dict[str, Place] = field(default_factory=dict)
    multimodal: list[dict] = field(default_factory=list)

    @property
    def observations(self) -> list:
        return [obs for entry in self.entries for obs in entry.observations]


def load_config(path: Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def _resolve_corpus(config: dict, input_dir: Optional[Path]) -> tuple[Path, Optional[Path]]:
    corpus = config.get("corpus", {})
    entries = None
    multimodal = None
    if input_dir and (Path(input_dir) / "entries.csv").exists():
        entries = Path(input_dir) / "entries.csv"
        mm = Path(input_dir) / "multimodal.md"
        multimodal = mm if mm.exists() else None
    if entries is None and corpus.get("entries"):
        entries = Path(corpus["entries"])
    if multimodal is None and corpus.get("multimodal"):
        candidate = Path(corpus["multimodal"])
        multimodal = candidate if candidate.exists() else None
    if entries is None:
        raise FileNotFoundError("No entries.csv found via input-dir or config.corpus.entries")
    return entries, multimodal


def build_entry(row: dict) -> DiaryEntry:
    return DiaryEntry(
        entry_uid=row.get("entry_uid", ""),
        entry_id=row.get("entry_id", ""),
        volume=int(row.get("volume") or 0),
        page_uid=row.get("page_uid", ""),
        page_id=row.get("page_id", ""),
        region_uid=row.get("region_uid") or None,
        scan=row.get("scan") or None,
        entry_date=normalize_date(row.get("date_raw"), row.get("date_norm")),
        verbatim_event_date=row.get("date_raw") or None,
        location_raw=row.get("location_raw") or None,
        text_clean=row.get("text_clean") or row.get("text_raw") or "",
    )


def run_pipeline(config: dict, input_dir: Optional[Path] = None) -> ExtractionResult:
    entries_csv, multimodal_path = _resolve_corpus(config, input_dir)
    volume = config.get("sample", {}).get("volume")
    resolver = build_resolver(config.get("taxa"))

    rows = read_entries(entries_csv, volume=int(volume) if volume is not None else None)
    result = ExtractionResult()
    for row in rows:
        entry = build_entry(row)
        place = normalize_place(entry.location_raw)
        if place is not None:
            result.places.setdefault(place.uid, place)
        entry.observations = extract_observations(entry, resolver, place)
        result.entries.append(entry)

    if multimodal_path is not None:
        entry_uids = {e.entry_uid for e in result.entries}
        result.multimodal = [r for r in read_multimodal(multimodal_path)
                             if r.get("entry_uid") in entry_uids]

    logger.info("pipeline: %d entries, %d observations, %d places, %d media",
                len(result.entries), len(result.observations),
                len(result.places), len(result.multimodal))
    return result
