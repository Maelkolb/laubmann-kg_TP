"""External linking stage: taxa -> GBIF backbone, persons -> Wikidata.

Runs after QA inside the pipeline (config section ``linking``; absent = off)
and writes its own review CSVs directly — the kg exporter aborts via SystemExit
on SHACL violations, which would silently lose review rows exactly when things
go wrong.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from laubmann_kg.linking.cache import JsonCache
from laubmann_kg.linking.persons import PERSON_REVIEW_FIELDS, link_persons
from laubmann_kg.linking.review import write_review_csv
from laubmann_kg.linking.taxa import TAXON_REVIEW_FIELDS, link_taxa

if TYPE_CHECKING:
    from laubmann_kg.pipeline import ExtractionResult

logger = logging.getLogger(__name__)

_AUTO_STATUSES = ("linked", "linked-broad", "reviewed")


def run_linking(result: "ExtractionResult", config: dict) -> dict:
    """Orchestrate both linking sections; linking must never abort the pipeline.

    ``config`` = the ``linking`` config section (offline, cache_dir, review_dir,
    limit, taxa.*, persons.*). Caches are flushed and review CSVs written in a
    finally block so partial runs still leave an auditable, resumable trail."""
    config = config or {}
    offline = bool(config.get("offline", False))
    cache_dir = Path(config.get("cache_dir", "data/cache/linking"))
    review_dir = Path(config.get("review_dir", "data/review"))
    limit = int(config.get("limit", 0) or 0)
    gbif_cache = JsonCache(cache_dir / "gbif_cache.json")
    wikidata_cache = JsonCache(cache_dir / "wikidata_cache.json")

    summary = {"taxa_linked": 0, "taxa_review": 0,
               "persons_linked": 0, "persons_review": 0}
    taxa_rows: list[dict] = []
    person_rows: list[dict] = []
    try:
        taxa_cfg = dict(config.get("taxa") or {})
        if taxa_cfg.get("enabled", True):
            taxa_cfg.setdefault("limit", limit)
            try:
                summary["taxa_linked"], taxa_rows = link_taxa(
                    result, taxa_cfg, gbif_cache, offline)
            except Exception as exc:  # noqa: BLE001
                logger.error("taxon linking failed: %s", exc)
            summary["taxa_review"] = sum(
                1 for r in taxa_rows if r.get("status") not in _AUTO_STATUSES)
        persons_cfg = dict(config.get("persons") or {})
        if persons_cfg.get("enabled", True):
            persons_cfg.setdefault("limit", limit)
            try:
                summary["persons_linked"], person_rows = link_persons(
                    result, persons_cfg, wikidata_cache, offline)
            except Exception as exc:  # noqa: BLE001
                logger.error("person linking failed: %s", exc)
            summary["persons_review"] = sum(
                1 for r in person_rows if r.get("rule") not in ("linked", "reviewed"))
    finally:
        gbif_cache.flush()
        wikidata_cache.flush()
        write_review_csv(taxa_rows, TAXON_REVIEW_FIELDS,
                         review_dir / "taxon_link_review.csv")
        write_review_csv(person_rows, PERSON_REVIEW_FIELDS,
                         review_dir / "person_link_review.csv")
    return summary


def run(config: Path, input_dir: Optional[Path], output_dir: Path) -> None:
    """Run the linking pipeline stage (populates caches + review CSVs without a
    full export; extraction rides the LLM response cache)."""
    from laubmann_kg.pipeline import load_config, run_pipeline
    logger.info("linking: config=%s input_dir=%s output_dir=%s",
                config, input_dir, output_dir)
    cfg = load_config(config)
    linking_cfg = cfg.get("linking") or {}  # tolerate a bare `linking:` key
    cfg["linking"] = linking_cfg
    linking_cfg["enabled"] = True
    linking_cfg.setdefault("review_dir", str(Path(output_dir) / "review"))
    run_pipeline(cfg, input_dir)  # the pipeline hook runs + logs run_linking
