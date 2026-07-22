"""LLM-backed observation extraction.

Renders the observation-extraction prompt per entry, calls a (cached) LLM client,
parses the structured JSON, and maps it to SHACL-safe ``Observation`` objects.
Scientific names from the model are backstopped/verified against the taxon
resolver; a taxon IRI is only taken from the resolver, never invented by the LLM.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from laubmann_kg.kg.model import Behaviour, DiaryEntry, Evidence, Observation, Place, Taxon
from laubmann_kg.llm.structured_output import extract_json, parse_structured
from laubmann_kg.normalization import vocabularies as vocab
from laubmann_kg.normalization.taxa import TaxonResolver

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path("schemas/observation.schema.json")


def load_array_schema(schema_path: Optional[Path] = None) -> dict:
    """Wrap the single-observation schema in an array schema for the LLM output."""
    path = Path(schema_path) if schema_path else _SCHEMA_PATH
    item = json.loads(path.read_text(encoding="utf-8"))
    item.pop("$schema", None)
    return {"type": "array", "items": item}


def _evidence_from(items: list) -> list[Evidence]:
    out: list[Evidence] = []
    for item in items or []:
        kind = (item.get("kind") or "").lower()
        if kind not in vocab.EVIDENCE_KINDS:
            continue
        if kind == "auditory":
            call_type = (item.get("call_type") or "call").lower()
            if call_type not in vocab.CALL_TYPES:
                call_type = "unknown"
            out.append(Evidence("auditory", "Lautäußerung", is_call=True,
                                call_type=call_type,
                                call_transcription=item.get("call_transcription") or "Ruf"))
        else:
            label = {"visual": "Sichtbeobachtung", "nest": "Nestfund / Brutnachweis",
                     "specimen": "Beleg / erlegtes Stück"}[kind]
            out.append(Evidence(kind, label))
    return out or [Evidence("visual", "Sichtbeobachtung")]


def _sanitize_count(value) -> Optional[int]:
    try:
        count = int(value)
        return count if count >= 1 else None
    except (TypeError, ValueError):
        return None


def _sanitize_qualifier(value) -> Optional[str]:
    return value if value in vocab.COUNT_QUALIFIERS else None


def map_items(entry: DiaryEntry, items: list, resolver: TaxonResolver,
              place: Optional[Place]) -> list[Observation]:
    observations: list[Observation] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        vernacular = (item.get("vernacular_de") or "").strip()
        if not vernacular:
            continue
        resolution = resolver.resolve(vernacular)
        llm_sci = (item.get("scientific_name") or "").strip() or None
        scientific = llm_sci or resolution.scientific_name
        behaviour = [Behaviour(str(b)) for b in (item.get("behaviour") or []) if str(b).strip()]
        if any(e.kind == "nest" for e in _evidence_from(item.get("evidence"))):
            behaviour.append(Behaviour("Brüten / besetztes Nest", reproductive_condition="breeding"))
        taxon = Taxon(
            vernacular_de=vernacular,
            scientific_name=scientific,
            taxon_iri=resolution.taxon_iri,
            match_method="llm" if llm_sci else resolution.match_method,
            confidence=item.get("confidence"),
            note=None if scientific else "vom LLM nicht sicher bestimmt",
        )
        observations.append(Observation(
            entry_uid=entry.entry_uid,
            taxon=taxon,
            verbatim_notes=(item.get("verbatim_notes") or entry.text_clean or vernacular).strip(),
            place=place,
            individual_count=_sanitize_count(item.get("individual_count")),
            count_qualifier=_sanitize_qualifier(item.get("count_qualifier")),
            evidence=_evidence_from(item.get("evidence")),
            behaviour=behaviour,
            index=index,
        ))
    return observations


def extract_observations_llm(entry: DiaryEntry, client, resolver: TaxonResolver,
                             place: Optional[Place], prompts, schema: dict) -> list[Observation]:
    text = entry.text_clean or ""
    if not text.strip():
        return []
    prompt = prompts.render(
        "observation_extraction",
        entry_date=entry.entry_date or "",
        location=entry.location_raw or "",
        text=text,
    )
    raw = client.complete(prompt)
    try:
        items = parse_structured(raw, schema)
    except Exception as exc:  # noqa: BLE001 - eyeball mode: log and degrade gracefully
        logger.warning("schema validation failed for %s (%s); using lenient parse",
                       entry.entry_id, exc)
        try:
            items = extract_json(raw)
        except Exception:
            logger.error("could not parse LLM output for %s; skipping. raw=%r",
                         entry.entry_id, (raw or "")[:800])
            return []
    if not isinstance(items, list):
        items = [items]
    return map_items(entry, items, resolver, place)
