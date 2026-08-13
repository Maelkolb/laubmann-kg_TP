"""Assemble a Darwin Core Archive (Event core + extensions) and zip it."""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

from laubmann_kg.dwca import event, measurement_or_fact, multimedia, occurrence
from laubmann_kg.dwca.meta_xml import FileSpec, build_meta_xml
from laubmann_kg.io.csv import write_rows

if TYPE_CHECKING:
    from laubmann_kg.pipeline import ExtractionResult

logger = logging.getLogger(__name__)

_EML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<eml:eml xmlns:eml="eml://ecoinformatics.org/eml-2.1.1" packageId="{package_id}"
         system="laubmann-kg" scope="system">
  <dataset>
    <title>{title}</title>
    <creator><individualName><surName>Laubmann</surName></individualName></creator>
    <abstract><para>Ornithological observations extracted from the field diaries
      of Alfred Laubmann. Sample export.</para></abstract>
    <intellectualRights><para>{license}</para></intellectualRights>
  </dataset>
</eml:eml>
"""


def build_archive(result: "ExtractionResult", output_dir: Path, config: dict | None = None) -> dict:
    config = config or {}
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    media_map = multimedia.media_by_entry(result)
    tables = {
        "event.txt": (event.FIELDS, event.build_events(result)),
        "occurrence.txt": (occurrence.FIELDS, occurrence.build_occurrences(result, media_map)),
        "measurementorfact.txt": (measurement_or_fact.FIELDS,
                                  measurement_or_fact.build_measurements(result)),
        "multimedia.txt": (multimedia.FIELDS, multimedia.build_multimedia(result)),
    }

    counts = {}
    for filename, (fields, rows) in tables.items():
        counts[filename] = write_rows(output_dir / filename, rows, fields)

    core = FileSpec("event", "event.txt", event.FIELDS)
    extensions = [
        FileSpec("occurrence", "occurrence.txt", occurrence.FIELDS),
        FileSpec("measurement_or_fact", "measurementorfact.txt", measurement_or_fact.FIELDS),
        FileSpec("multimedia", "multimedia.txt", multimedia.FIELDS),
    ]
    (output_dir / "meta.xml").write_text(build_meta_xml(core, extensions), encoding="utf-8")
    (output_dir / "eml.xml").write_text(
        _EML_TEMPLATE.format(
            package_id="laubmann-kg-sample",
            title=config.get("publisher", "Laubmann KG Project") + " – Sample",
            license=config.get("license", "CC-BY-4.0"),
        ),
        encoding="utf-8",
    )

    zip_path = output_dir / "laubmann_sample_dwca.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in [*tables.keys(), "meta.xml", "eml.xml"]:
            archive.write(output_dir / name, arcname=name)

    logger.info("wrote DwC-A to %s (%s)", zip_path, counts)
    return {"dir": str(output_dir), "zip": str(zip_path), "counts": counts}
