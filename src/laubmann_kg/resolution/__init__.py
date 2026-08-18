"""Entity-resolution stage: merge spellings/variants that denote the same taxon,
person, place or habitat into one node (config section ``resolution``).

Runs after linking (it uses GBIF keys and Wikidata items as evidence) and
before the graph is built. Every merge is written to a review CSV per section
(``review_dir/{taxon,person,place,habitat}_merges.csv``, decision contract in
``resolution/common.py``); ``reviewed_csv`` per section feeds decisions back.
Never aborts the pipeline.

    resolution:
      enabled: true
      review_dir: data/review
      taxa:     {enabled: true, merge_on_scientific_name: true, reviewed_csv: null}
      persons:  {enabled: true, merge_bare_surname: true, reviewed_csv: null}
      places:   {enabled: true, similarity: 0.9, reviewed_csv: null}
      habitats: {enabled: true, similarity: 0.85, reviewed_csv: null}
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from laubmann_kg.resolution.common import Decisions, MergeRow, write_merge_rows
from laubmann_kg.resolution.persons import merge_persons
from laubmann_kg.resolution.places import merge_habitats, merge_places
from laubmann_kg.resolution.taxa import merge_taxa

if TYPE_CHECKING:
    from laubmann_kg.pipeline import ExtractionResult

logger = logging.getLogger(__name__)

_SECTIONS = (("taxa", merge_taxa, "taxon_merges.csv"),
             ("persons", merge_persons, "person_merges.csv"),
             ("places", merge_places, "place_merges.csv"),
             ("habitats", merge_habitats, "habitat_merges.csv"))


def run_resolution(result: "ExtractionResult", config: dict) -> dict:
    config = config or {}
    review_dir = Path(config.get("review_dir", "data/review"))
    summary: dict = {}
    for name, fn, filename in _SECTIONS:
        sec = dict(config.get(name) or {})
        if not sec.get("enabled", True):
            continue
        reviewed = sec.get("reviewed_csv") or (review_dir / filename if (review_dir / filename).exists() else None)
        decisions = Decisions.load(reviewed)
        rows: list[MergeRow] = []
        try:
            merged, rows = fn(result, sec, decisions)
            summary[f"{name}_merged"] = merged
            summary[f"{name}_candidates"] = sum(1 for r in rows if r.status == "candidate")
        except Exception as exc:  # noqa: BLE001 - resolution must never abort the pipeline
            logger.error("%s resolution failed: %s", name, exc)
        finally:
            try:
                write_merge_rows(rows, review_dir / filename)
            except Exception as exc:  # noqa: BLE001
                logger.error("could not write %s: %s", filename, exc)
    return summary
