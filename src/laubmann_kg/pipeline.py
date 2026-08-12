"""Corpus → in-memory model pipeline shared by the extraction and export stages.

Loads the frozen corpus interface (entries.csv + multimodal), builds domain
objects, and runs rule-based extraction. Switching from the sample to the
deduped corpus is a path change in the config, not a code change.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from laubmann_kg.extraction.citations import extract_citations
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
    qa_flags: list = field(default_factory=list)

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

    from laubmann_kg.extraction.llm_observations import extract_observations_llm, load_entry_schema
    from laubmann_kg.llm.cache import LLMCache
    from laubmann_kg.llm.clients import build_client
    from laubmann_kg.llm.prompts import PromptLibrary

    cache = LLMCache(Path(extraction["cache_dir"])) if extraction.get("cache_dir") else None
    client = build_client(cache=cache, config={
        "backend": extraction.get("provider", "google"),
        "model": extraction.get("model"),
        "api_key_env": extraction.get("api_key_env", "GOOGLE_API_KEY"),
        "temperature": extraction.get("temperature", 0.0),
        "max_output_tokens": extraction.get("max_output_tokens", 4096),
        "timeout": extraction.get("timeout", 120),
        "thinking_level": extraction.get("thinking_level"),
        "retry_attempts": extraction.get("retry_attempts", 3),
        "retry_backoff": extraction.get("retry_backoff", 2.0),
    })
    prompts = PromptLibrary(Path(extraction.get("prompt_dir", "prompts")))
    schema = load_entry_schema(extraction.get("schema"))
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
    extraction_cfg = config.get("extraction", {})
    backend = (extraction_cfg.get("backend") or "offline").lower()
    concurrency = max(1, int(extraction_cfg.get("concurrency", 1)))
    logger.info("extracting %d entries (volume=%s, backend=%s, concurrency=%d)",
                total, volume, backend, concurrency)

    result = ExtractionResult()

    # Sequential prep: entries, citations, and the shared places dict.
    jobs: list[tuple] = []
    for row in rows:
        entry = build_entry(row)
        entry.citations = [c.verbatim for c in extract_citations(entry.text_clean)]
        place = normalize_place(entry.location_raw)
        if place is not None:
            result.places.setdefault(place.uid, place)
        jobs.append((entry, place))

    def _extract_one(job):
        entry, place = job
        try:
            return extract(entry, place)
        except Exception as exc:  # noqa: BLE001 - one bad entry must not abort the run
            logger.error("%s extraction failed: %s -- skipping", entry.entry_id, exc)
            return None

    # Parallel extraction; executor.map preserves input order, so results,
    # logging, and downstream exports stay deterministic.
    empty = failed = 0
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for i, (job, observations) in enumerate(zip(jobs, pool.map(_extract_one, jobs)), 1):
            entry, _ = job
            if observations is None:
                failed += 1
                observations = []
            entry.observations = observations
            if entry.citations:  # attach the entry's source attribution to its occurrences
                remark = "Quellenangabe: " + "; ".join(entry.citations)
                for obs in entry.observations:
                    if obs.occurrence_remarks is None:
                        obs.occurrence_remarks = remark
            if not entry.observations:
                empty += 1
            result.entries.append(entry)
            logger.info("[%d/%d] %s -> %d observations", i, total, entry.entry_id,
                        len(entry.observations))

    qa_cfg = config.get("qa", {})
    if qa_cfg.get("enabled", True):
        from laubmann_kg.qa import run_qa
        before = len(result.entries)
        kept, result.qa_flags = run_qa(result.entries, qa_cfg)
        result.entries = kept
        logger.info("QA: %d flags, %d/%d entries excluded", len(result.qa_flags),
                    before - len(kept), before)

    if multimodal_path is not None:
        entry_uids = {e.entry_uid for e in result.entries}
        result.multimodal = [r for r in read_multimodal(multimodal_path)
                             if r.get("entry_uid") in entry_uids]

    logger.info("pipeline: %d entries (%d empty, %d failed), %d observations, "
                "%d travel events, %d persons, %d places, %d media",
                len(result.entries), empty, failed, len(result.observations),
                sum(len(e.travel_events) for e in result.entries),
                sum(len(e.persons) for e in result.entries),
                len(result.places), len(result.multimodal))
    return result
