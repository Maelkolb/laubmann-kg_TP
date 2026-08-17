"""Export a Darwin Core Archive from the extracted observations."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from laubmann_kg.dwca.archive import build_archive
from laubmann_kg.dwca.validate import validate_archive
from laubmann_kg.pipeline import load_config, run_pipeline

logger = logging.getLogger(__name__)


def export(config: dict, input_dir: Optional[Path], output_dir: Path,
           validate: bool = True) -> dict:
    result = run_pipeline(config, input_dir)
    dwca_dir = Path(output_dir) / "dwca"
    # the dwca: config section carries EML metadata (title, package_id,
    # publisher, license); result.provenance feeds methods/measurementMethod
    summary = build_archive(result, dwca_dir, config.get("dwca", {}))
    summary["entries"] = len(result.entries)
    summary["dated_entries"] = sum(1 for e in result.entries if e.entry_date)
    summary["observations"] = len(result.observations)
    summary["absences"] = sum(1 for o in result.observations
                              if o.occurrence_status == "absent")
    summary["places"] = len(result.places)
    summary["media"] = len(result.multimodal)
    summary["provenance"] = dict(result.provenance or {})
    if validate:
        problems = validate_archive(dwca_dir)
        summary["valid"] = not problems
        summary["problems"] = problems
        if problems:
            raise SystemExit(f"DwC-A validation failed: {problems}")
    return summary


def run(config: Path, input_dir: Path, output_dir: Path) -> None:
    """Run the dwca export pipeline stage."""
    logger.info("dwca export: config=%s input_dir=%s output_dir=%s", config, input_dir, output_dir)
    summary = export(load_config(config), input_dir, output_dir)
    logger.info("dwca export summary: %s", summary)
