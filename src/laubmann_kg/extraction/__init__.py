"""Extract structured observations and write them as JSON-LD-ready records."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from laubmann_kg.io.json import write_json

logger = logging.getLogger(__name__)


def _observation_record(entry, obs) -> dict:
    taxon = obs.taxon
    return {
        "occurrence_uid": obs.uid,
        "entry_uid": entry.entry_uid,
        "entry_id": entry.entry_id,
        "entry_date": entry.entry_date,
        "entry_kind": entry.entry_kind,
        "location_raw": entry.location_raw,
        "entry_place": entry.place.name if entry.place else None,
        "place": obs.place.name if obs.place else None,
        "locality_verbatim": obs.locality.verbatim if obs.locality else None,
        "vernacular_de": taxon.vernacular_de,
        "taxon_rank": taxon.rank,
        "is_bird": taxon.is_bird,
        "scientific_name": taxon.scientific_name,
        "taxon_iri": taxon.taxon_iri,
        "match_method": taxon.match_method,
        "confidence": taxon.confidence,
        "occurrence_status": obs.occurrence_status,
        "individual_count": obs.individual_count,
        "count_min": obs.count_min,
        "count_max": obs.count_max,
        "count_qualifier": obs.count_qualifier,
        "sex": obs.sex,
        "life_stage": obs.life_stage,
        "breeding_evidence": obs.breeding_evidence,
        "vitality": obs.vitality,
        "movement_kind": obs.movement_kind,
        "flight_direction": obs.flight_direction,
        "identification_qualifier": obs.identification_qualifier,
        "event_date": obs.event_date or entry.entry_date,
        "event_time": obs.event_time,
        "evidence": [e.kind for e in obs.evidence],
        "behaviour": [b.label for b in obs.behaviour],
        "habitat": obs.habitat.label if obs.habitat else None,
        "verbatim_notes": obs.verbatim_notes,
        "record_type": obs.record_type,
        "observer": obs.observer.name if obs.observer else None,
        "literature_citation": obs.literature_citation,
        "gbif_key": taxon.gbif_key,
    }


def export(config: dict, input_dir: Optional[Path], output_dir: Path) -> dict:
    from laubmann_kg.pipeline import run_pipeline
    result = run_pipeline(config, input_dir)
    records = [_observation_record(entry, obs)
               for entry in result.entries for obs in entry.observations]
    out = Path(output_dir) / "observations.json"
    write_json(out, records)
    summary = {"entries": len(result.entries), "observations": len(records),
               "output": str(out)}
    return summary


def run(config: Path, input_dir: Path, output_dir: Path) -> None:
    """Run the extraction pipeline stage."""
    from laubmann_kg.pipeline import load_config
    logger.info("extraction: config=%s input_dir=%s output_dir=%s", config, input_dir, output_dir)
    summary = export(load_config(config), input_dir, output_dir)
    logger.info("extraction summary: %s", summary)
