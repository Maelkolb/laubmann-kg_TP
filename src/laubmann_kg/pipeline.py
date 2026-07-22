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


def _build_extractor(config: dict):
    """Return an ``extract(entry, place) -> list[Observation]`` callable selected
    by ``extraction.backend`` (offline rule-based, or an LLM provider)."""
    extraction = config.get("extraction", {})
    backend = (extraction.get("backend") or "offline").lower()
    resolver = build_resolver(config.get("taxa"))

    if backend in ("offline", "rule", "rules", "gazetteer"):
        return lambda entry, place: extract_observations(entry, resolver, place)

    from laubmann_kg.extraction.llm_observations import extract_observations_llm, load_array_schema
    from laubmann_kg.llm.clients import build_client
    from laubmann_kg.llm.prompts import PromptLibrary

    client = build_client({
        "backend": extraction.get("provider", "google"),
        "model": extraction.get("model"),
        "api_key_env": extraction.get("api_key_env", "GOOGLE_API_KEY"),
        "temperature": extraction.get("temperature", 0.0),
        "max_output_tokens": extraction.get("max_output_tokens", 4096),
        "timeout": extraction.get("timeout", 120),
    })
    prompts = PromptLibrary(Path(extraction.get("prompt_dir", "prompts")))
    schema = load_array_schema(extraction.get("schema"))
    logger.info("extraction backend=%s provider=%s model=%s", backend,
                extraction.get("provider", "google"), extraction.get("model"))
    return lambda entry, place: extract_observations_llm(
        entry, client, resolver, place, prompts, schema)


def run_pipeline(config: dict, input_dir: Optional[Path] = None) -> ExtractionResult:
    entries_csv, multimodal_path = _resolve_corpus(config, input_dir)
    volume = config.get("sample", {}).get("volume")
    extract = _build_extractor(config)

    rows = read_entries(entries_csv, volume=int(volume) if volume is not None else None)
    total = len(rows)
    backend = (config.get("extraction", {}).get("backend") or "offline").lower()
    logger.info("extracting %d entries (volume=%s, backend=%s)", total, volume, backend)

    result = ExtractionResult()
    empty = failed = 0
    for i, row in enumerate(rows, 1):
        entry = build_entry(row)
        place = normalize_place(entry.location_raw)
        if place is not None:
            result.places.setdefault(place.uid, place)
        try:
            entry.observations = extract(entry, place)
        except Exception as exc:  # noqa: BLE001 - one bad entry must not abort the run
            logger.error("[%d/%d] %s extraction failed: %s -- skipping", i, total,
                         entry.entry_id, exc)
            entry.observations = []
            failed += 1
        if not entry.observations:
            empty += 1
        result.entries.append(entry)
        logger.info("[%d/%d] %s -> %d observations", i, total, entry.entry_id,
                    len(entry.observations))

    if multimodal_path is not None:
        entry_uids = {e.entry_uid for e in result.entries}
        result.multimodal = [r for r in read_multimodal(multimodal_path)
                             if r.get("entry_uid") in entry_uids]

    logger.info("pipeline: %d entries (%d empty, %d failed), %d observations, "
                "%d places, %d media", len(result.entries), empty, failed,
                len(result.observations), len(result.places), len(result.multimodal))
    return result
