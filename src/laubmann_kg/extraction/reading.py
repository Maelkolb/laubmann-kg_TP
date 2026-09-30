"""Visual reading: the transcription of each entry checked against its page scans.

Runs before extraction (config section ``reading``). One call per entry: the
page scan(s) the entry is written on plus its transcription
(prompts/transcript_reading.md) -> ``{"quality", "corrections": [{"old",
"new"}]}``. Each correction whose ``old`` occurs in the entry text is applied,
so the extraction model reads the corrected entry and everything it derives
(species, counts, places, dates) follows from the scan; the text as
transcribed is kept (``DiaryEntry.text_transcribed``), every correction is
listed in ``review/transcript_corrections.csv`` (the review/text_corrections
contract, for confirmation in the validation UI) and summarised as a
skos:note of the entry. Answers are cached like the extraction's
(sha256 of model, prompt, page ids, media resolution).
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from laubmann_kg.kg.model import DiaryEntry
from laubmann_kg.llm.structured_output import extract_json
from laubmann_kg.normalization import vocabularies as vocab

logger = logging.getLogger(__name__)


# an insertion longer than this is most likely text of a neighbouring entry on
# the same page: it is listed for review but not applied
MAX_INSERT_CHARS = 400


def apply_reading(entry: DiaryEntry, raw) -> None:
    """Apply ``{"quality", "corrections"}`` to the entry text (first occurrence
    of each ``old``, whitespace tolerant); unmatched corrections and oversized
    insertions are kept with ``applied = False`` for QA and review."""
    if not isinstance(raw, dict):
        return
    entry.transcript_quality = vocab.normalize_enum(raw.get("quality"), vocab.TRANSCRIPT_QUALITY)
    text = entry.text_clean or ""
    original = text
    out: list[tuple[str, str, bool]] = []
    for item in raw.get("corrections") or []:
        if not isinstance(item, dict):
            continue
        old, new = item.get("old"), item.get("new")
        if not isinstance(old, str) or not old.strip() or not isinstance(new, str) or old == new:
            continue
        applied = False
        if len(new) - len(old) > MAX_INSERT_CHARS:
            out.append((old, new, False))
            continue
        if old in text:
            text = text.replace(old, new, 1)
            applied = True
        else:
            pattern = r"\s+".join(re.escape(tok) for tok in old.split())
            m = re.search(pattern, text) if pattern else None
            if m:
                text = text[:m.start()] + new + text[m.end():]
                applied = True
        out.append((old, new, applied))
    entry.transcript_corrections = out
    if text != original:
        entry.text_transcribed = original
        entry.text_clean = text


def read_entry(entry: DiaryEntry, client, prompts, images) -> bool:
    """One reading call; returns True when the entry was checked."""
    text = entry.text_clean or ""
    if not text.strip():
        return False
    page_images = images(entry) if images is not None else []
    if not page_images:
        return False                      # nothing to compare with
    prompt = prompts.render("transcript_reading", date_raw=entry.verbatim_event_date or "",
                            location=entry.location_raw or "", text=text,
                            before=entry.neighbour_before or "", after=entry.neighbour_after or "")
    raw = client.complete(prompt, images=page_images)
    if getattr(raw, "truncated", False):
        entry.flags.append("reading_truncated")
    try:
        data = extract_json(raw)
    except Exception:  # noqa: BLE001 - a failed reading leaves the transcription as it is
        logger.warning("unreadable reading answer for %s", entry.entry_id)
        return False
    apply_reading(entry, data if isinstance(data, dict) else {})
    return True


def run_reading(entries: list[DiaryEntry], config: dict, images) -> dict:
    """Check every entry's transcription against its scans (config ``reading``:
    provider, model, cache_dir, prompt_dir, media_resolution, concurrency,
    thinking_level, max_output_tokens, context_cache)."""
    from laubmann_kg.llm.cache import LLMCache
    from laubmann_kg.llm.clients import build_client
    from laubmann_kg.llm.prompts import PromptLibrary

    cache = LLMCache(Path(config.get("cache_dir", "data/cache/reading_v1")))
    client = build_client(cache=cache, config={
        "backend": config.get("provider", "google"),
        "model": config.get("model", "gemini-3.8-flash"),
        "api_key_env": config.get("api_key_env", "GOOGLE_API_KEY"),
        "temperature": config.get("temperature", 0.0),
        "max_output_tokens": config.get("max_output_tokens", 16384),
        "timeout": config.get("timeout", 600),
        "thinking_level": config.get("thinking_level", "low"),
        "context_cache": config.get("context_cache", True),
        "media_resolution": config.get("media_resolution", "MEDIA_RESOLUTION_HIGH"),
        "retry_attempts": config.get("retry_attempts", 3),
        "retry_backoff": config.get("retry_backoff", 2.0),
    })
    prompts = PromptLibrary(Path(config.get("prompt_dir", "prompts")))

    def one(entry):
        try:
            return read_entry(entry, client, prompts, images)
        except Exception as exc:  # noqa: BLE001 - one failed reading must not stop the run
            logger.error("%s reading failed: %s", entry.entry_id, exc)
            return False

    checked = 0
    with ThreadPoolExecutor(max_workers=max(1, int(config.get("concurrency", 8)))) as pool:
        for i, (entry, ok) in enumerate(zip(entries, pool.map(one, entries)), 1):
            checked += bool(ok)
            if i % 100 == 0 or i == len(entries):
                logger.info("reading [%d/%d] %s", i, len(entries), entry.entry_id)
    corrected = sum(1 for e in entries if e.text_transcribed is not None)
    quality: dict[str, int] = {}
    for e in entries:
        if e.transcript_quality:
            quality[e.transcript_quality] = quality.get(e.transcript_quality, 0) + 1
    return {"checked": checked, "corrected": corrected, "quality": quality,
            "corrections": sum(len(e.transcript_corrections) for e in entries),
            "unmatched": sum(1 for e in entries for c in e.transcript_corrections if not c[2])}


def reading_prompt_sha(prompt_dir: Optional[Path]) -> Optional[str]:
    import hashlib
    path = Path(prompt_dir or "prompts") / "transcript_reading.md"
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
