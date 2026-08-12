"""LLM-backed entry extraction (observations, travel, persons).

Renders the entry-extraction prompt, calls a (cached) LLM client, parses the
structured JSON, and maps it to SHACL-safe domain objects. The model is given
wide latitude in reading the entry; correctness is enforced here: scientific
names are backstopped/verified against the taxon resolver (a taxon IRI is only
taken from the resolver, never invented by the LLM), transport modes and
qualifiers are folded onto the controlled vocabularies, travel legs must end up
with both a departure and an arrival place or they are dropped, and times only
become xsd:dateTime when they parse and are consistent.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from laubmann_kg.kg.model import (
    Behaviour,
    DiaryEntry,
    Evidence,
    Habitat,
    Observation,
    Person,
    Place,
    TravelEvent,
    TravelLeg,
    Taxon,
)
from laubmann_kg.llm.structured_output import extract_json, parse_structured
from laubmann_kg.normalization import vocabularies as vocab
from laubmann_kg.normalization.places import normalize_place
from laubmann_kg.normalization.taxa import TaxonResolver

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path("schemas/observation.schema.json")
_ENTRY_SCHEMA_PATH = Path("schemas/entry_extraction.schema.json")

_TIME_RE = re.compile(r"^\s*(\d{1,2})[:.h](\d{2})\s*$")

_PERSON_ROLES = ("companion", "source", "collector", "cited-author", "other")


def load_array_schema(schema_path: Optional[Path] = None) -> dict:
    """Wrap the single-observation schema in an array schema (legacy response
    format; kept for configs/tests that still exercise it)."""
    path = Path(schema_path) if schema_path else _SCHEMA_PATH
    item = json.loads(path.read_text(encoding="utf-8"))
    item.pop("$schema", None)
    return {"type": "array", "items": item}


def load_entry_schema(schema_path: Optional[Path] = None) -> dict:
    """Entry-level response schema ({observations, travel_events, persons}).

    The observation item schema is injected from ``schema_path`` (default
    schemas/observation.schema.json) so it stays single-source."""
    entry = json.loads(_ENTRY_SCHEMA_PATH.read_text(encoding="utf-8"))
    entry.pop("$schema", None)
    item = json.loads((Path(schema_path) if schema_path else _SCHEMA_PATH)
                      .read_text(encoding="utf-8"))
    item.pop("$schema", None)
    entry["properties"]["observations"]["items"] = item
    return entry


def _as_list(value) -> list:
    """Coerce model output to a list: None → [], list → list (minus Nones),
    scalar/dict → [value]. Guards against a bare string being iterated
    character-by-character downstream."""
    if value is None:
        return []
    if isinstance(value, list):
        return [v for v in value if v is not None]
    return [value]


def _evidence_from(items) -> list[Evidence]:
    out: list[Evidence] = []
    for item in _as_list(items):
        if not isinstance(item, dict):
            continue
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
        behaviour = [Behaviour(str(b).strip()) for b in _as_list(item.get("behaviour"))
                     if str(b).strip()]
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
        habitat = (item.get("habitat") or "").strip()
        observations.append(Observation(
            entry_uid=entry.entry_uid,
            taxon=taxon,
            verbatim_notes=(item.get("verbatim_notes") or entry.text_clean or vernacular).strip(),
            place=place,
            individual_count=_sanitize_count(item.get("individual_count")),
            count_qualifier=_sanitize_qualifier(item.get("count_qualifier")),
            evidence=_evidence_from(item.get("evidence")),
            behaviour=behaviour,
            habitat=Habitat(habitat) if habitat else None,
            index=index,
        ))
    return observations


def _travel_place(name) -> Optional[Place]:
    """Resolve a travel place via the gazetteer, falling back to a minimal
    Place carrying the verbatim name (PlaceShape only requires a label)."""
    raw = (str(name) if name is not None else "").strip()
    if not raw:
        return None
    return normalize_place(raw) or Place(verbatim=raw)


def _iso_datetime(entry_date: Optional[str], raw) -> Optional[str]:
    """Combine the entry's ISO date with a stated clock time → xsd:dateTime."""
    if not entry_date or raw is None:
        return None
    m = _TIME_RE.match(str(raw))
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2))
    if hour > 23 or minute > 59:
        return None
    return f"{entry_date}T{hour:02d}:{minute:02d}:00"


def map_travel(entry: DiaryEntry, items: list,
               entry_place: Optional[Place]) -> list[TravelEvent]:
    """Map LLM travel events onto SHACL-safe TravelEvent/TravelLeg objects.

    A leg missing its departure inherits the previous leg's arrival, then the
    entry's own place (diary semantics: the entry is written somewhere). Legs
    that still lack either endpoint are dropped; events without surviving legs
    are dropped (TravelEventShape requires >= 1 leg)."""
    events: list[TravelEvent] = []
    for ti, item in enumerate(_as_list(items)):
        if not isinstance(item, dict):
            continue
        raw_legs = _as_list(item.get("legs"))
        if not raw_legs and ("arrival_place" in item or "departure_place" in item):
            # The model frequently emits the event as a bare leg object without
            # the legs wrapper — treat the event itself as its single leg.
            raw_legs = [item]
        legs: list[TravelLeg] = []
        prev_arrival: Optional[Place] = None
        for raw_leg in raw_legs:
            if not isinstance(raw_leg, dict):
                continue
            arrival = _travel_place(raw_leg.get("arrival_place"))
            departure = (_travel_place(raw_leg.get("departure_place"))
                         or prev_arrival or entry_place)
            if arrival is None or departure is None:
                logger.debug("dropping travel leg without both endpoints (%s)",
                             entry.entry_id)
                continue
            dep_t = _iso_datetime(entry.entry_date, raw_leg.get("departure_time"))
            arr_t = _iso_datetime(entry.entry_date, raw_leg.get("arrival_time"))
            if dep_t and arr_t and arr_t <= dep_t:
                arr_t = None  # same-day contradiction (overnight or misread) — keep departure
            legs.append(TravelLeg(
                departure_place=departure,
                arrival_place=arrival,
                via_places=tuple(p for p in (_travel_place(v) for v in
                                             _as_list(raw_leg.get("via_places"))) if p),
                transport_mode=vocab.normalize_transport_mode(raw_leg.get("transport_mode")),
                departure_time=dep_t,
                arrival_time=arr_t,
                verbatim=(raw_leg.get("verbatim") or "").strip() or None,
            ))
            prev_arrival = arrival
        if legs:
            events.append(TravelEvent(entry_uid=entry.entry_uid, legs=legs, index=ti))
    return events


def map_persons(items: list) -> list[Person]:
    out: list[Person] = []
    seen: set[str] = set()
    for item in _as_list(items):
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        role = item.get("role")
        out.append(Person(name=name, role=role if role in _PERSON_ROLES else None))
    return out


def extract_observations_llm(entry: DiaryEntry, client, resolver: TaxonResolver,
                             place: Optional[Place], prompts, schema: dict) -> list[Observation]:
    """One LLM call per entry. Returns the observations; travel_events and
    persons are attached to ``entry`` directly. Legacy array-only responses
    (old caches, old schema configs) are accepted as bare observations."""
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
        data = parse_structured(raw, schema)
    except Exception as exc:  # noqa: BLE001 - eyeball mode: log and degrade gracefully
        logger.warning("schema validation failed for %s (%s); using lenient parse",
                       entry.entry_id, exc)
        try:
            data = extract_json(raw)
        except Exception:
            logger.error("could not parse LLM output for %s; skipping. raw=%r",
                         entry.entry_id, (raw or "")[:800])
            return []
    if isinstance(data, list):
        data = {"observations": data}
    if not isinstance(data, dict):
        data = {}
    entry.travel_events = map_travel(entry, data.get("travel_events"), place)
    entry.persons = map_persons(data.get("persons"))
    items = data.get("observations") or []
    if not isinstance(items, list):
        items = [items]
    return map_items(entry, items, resolver, place)
