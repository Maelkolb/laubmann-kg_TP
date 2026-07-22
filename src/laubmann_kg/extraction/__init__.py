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
        "location_raw": entry.location_raw,
        "vernacular_de": taxon.vernacular_de,
        "scientific_name": taxon.scientific_name,
        "taxon_iri": taxon.taxon_iri,
        "match_method": taxon.match_method,
        "confidence": taxon.confidence,
        "individual_count": obs.individual_count,
        "count_qualifier": obs.count_qualifier,
        "evidence": [e.kind for e in obs.evidence],
        "behaviour": [b.label for b in obs.behaviour],
        "verbatim_notes": obs.verbatim_notes,
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
