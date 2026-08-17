"""Assemble a Darwin Core Archive (Event core + extensions) and zip it."""

from __future__ import annotations

import datetime as _dt
import logging
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Optional
from xml.sax.saxutils import escape, quoteattr

from laubmann_kg.dwca import event, measurement_or_fact, multimedia, occurrence
from laubmann_kg.dwca.meta_xml import FileSpec, build_meta_xml
from laubmann_kg.io.csv import write_rows

if TYPE_CHECKING:
    from laubmann_kg.pipeline import ExtractionResult

logger = logging.getLogger(__name__)

DEFAULT_TITLE = "Laubmann ornithological field diaries 1917–1965 — observations"
DEFAULT_PACKAGE_ID = "laubmann-kg-full"
DEFAULT_PUBLISHER = "Laubmann KG Project"
DEFAULT_LICENSE = "CC-BY-4.0"
DEFAULT_ZIP_NAME = "laubmann_sample_dwca.zip"   # referenced by docs/notebooks

_LICENSE_LINKS = {
    "CC-BY-4.0": ("https://creativecommons.org/licenses/by/4.0/",
                  "Creative Commons Attribution 4.0"),
    "CC-BY-SA-4.0": ("https://creativecommons.org/licenses/by-sa/4.0/",
                     "Creative Commons Attribution-ShareAlike 4.0"),
    "CC0-1.0": ("https://creativecommons.org/publicdomain/zero/1.0/",
                "Creative Commons Zero 1.0"),
}

DEFAULT_ABSTRACT = (
    "Ornithological observations extracted from the handwritten field diaries of "
    "Alfred Laubmann (Bavarian ornithologist, 1886–1965). Each diary entry is a "
    "sampling event; each bird record within an entry is an occurrence. Records "
    "were transcribed from page scans and structured by a documented extraction "
    "pipeline; verbatim wording is retained in fieldNotes and occurrenceRemarks, "
    "and categorical facts (evidence, count qualifier, breeding evidence, movement) "
    "are published as ExtendedMeasurementOrFact rows with concept IRIs from the "
    "project vocabulary."
)


def _rights(license_id: str) -> str:
    link = _LICENSE_LINKS.get(license_id)
    if link is None:
        return f"<intellectualRights><para>{escape(license_id)}</para></intellectualRights>"
    url, title = link
    return ("<intellectualRights><para>This work is licensed under a "
            f'<ulink url="{escape(url)}"><citetitle>{escape(title)}</citetitle></ulink>'
            " License.</para></intellectualRights>")


def _temporal_range(result: "ExtractionResult") -> Optional[tuple[str, str]]:
    dates = []
    for entry in result.entries:
        for value in (entry.entry_date, getattr(entry, "entry_date_end", None)):
            if value:
                dates.append(value)
        for obs in entry.observations:
            if obs.event_date:
                dates.append(obs.event_date)
    if not dates:
        return None
    return min(dates), max(dates)


def _bbox(result: "ExtractionResult") -> Optional[tuple[float, float, float, float]]:
    """(west, east, south, north) over every place with coordinates."""
    places = list(result.places.values())
    for entry in result.entries:
        if entry.place is not None:
            places.append(entry.place)
        for obs in entry.observations:
            if obs.place is not None:
                places.append(obs.place)
    lats = [p.lat for p in places if p.lat is not None and p.long is not None]
    longs = [p.long for p in places if p.lat is not None and p.long is not None]
    if not lats:
        return None
    return min(longs), max(longs), min(lats), max(lats)


def _coverage(result: "ExtractionResult") -> str:
    lines = ["<coverage>"]
    bbox = _bbox(result)
    if bbox is not None:
        west, east, south, north = bbox
        lines += [
            "  <geographicCoverage>",
            "    <geographicDescription>Localities named in the diary entries, "
            "georeferenced to settlement/locality centroids</geographicDescription>",
            "    <boundingCoordinates>",
            f"      <westBoundingCoordinate>{west:.4f}</westBoundingCoordinate>",
            f"      <eastBoundingCoordinate>{east:.4f}</eastBoundingCoordinate>",
            f"      <northBoundingCoordinate>{north:.4f}</northBoundingCoordinate>",
            f"      <southBoundingCoordinate>{south:.4f}</southBoundingCoordinate>",
            "    </boundingCoordinates>",
            "  </geographicCoverage>",
        ]
    temporal = _temporal_range(result)
    if temporal is not None:
        start, end = temporal
        lines += [
            "  <temporalCoverage>",
            "    <rangeOfDates>",
            f"      <beginDate><calendarDate>{escape(start)}</calendarDate></beginDate>",
            f"      <endDate><calendarDate>{escape(end)}</calendarDate></endDate>",
            "    </rangeOfDates>",
            "  </temporalCoverage>",
        ]
    lines += [
        "  <taxonomicCoverage>",
        "    <generalTaxonomicCoverage>Birds (class Aves); occasional non-avian "
        "records are flagged via kingdom/class</generalTaxonomicCoverage>",
        "    <taxonomicClassification>",
        "      <taxonRankName>class</taxonRankName>",
        "      <taxonRankValue>Aves</taxonRankValue>",
        "      <commonName>Vögel</commonName>",
        "    </taxonomicClassification>",
        "  </taxonomicCoverage>",
        "</coverage>",
    ]
    return "\n    ".join(lines)


def _methods(result: "ExtractionResult") -> str:
    prov = result.provenance or {}
    method = prov.get("method") or measurement_or_fact.DEFAULT_METHOD
    details = []
    if prov.get("model"):
        details.append(f"model: {prov['model']}")
    if prov.get("prompt"):
        details.append(f"prompt: {prov['prompt']}")
    if prov.get("prompt_sha256"):
        details.append(f"prompt sha256: {prov['prompt_sha256']}")
    if prov.get("temperature") is not None:
        details.append(f"temperature: {prov['temperature']}")
    if prov.get("started_at"):
        details.append(f"run started: {prov['started_at']}")
    para = escape(method[0].upper() + method[1:]) if method else ""
    if details:
        para += " (" + escape("; ".join(details)) + ")"
    return (
        "<methods>\n"
        "      <methodStep><description>\n"
        f"        <para>{para}. Entries were transcribed from page scans; the "
        "extraction step reads each entry and emits structured observations "
        "(taxon, count, evidence, behaviour, place, date) that are validated "
        "against a controlled vocabulary and SHACL shapes before export.</para>\n"
        "      </description></methodStep>\n"
        "      <sampling>\n"
        "        <studyExtent><description><para>Complete transcribed diary "
        "corpus, one event per dated entry.</para></description></studyExtent>\n"
        "        <samplingDescription><para>Opportunistic field observations "
        "as noted by the diarist; no standardised effort.</para></samplingDescription>\n"
        "      </sampling>\n"
        "    </methods>")


def build_eml(result: "ExtractionResult", config: dict | None = None,
              today: Optional[_dt.date] = None) -> str:
    """EML 2.1.1 dataset metadata for the archive (config = the ``dwca:``
    section: title, package_id, publisher, license, abstract)."""
    config = config or {}
    today = today or _dt.date.today()
    publisher = config.get("publisher", DEFAULT_PUBLISHER)
    title = config.get("title", DEFAULT_TITLE)
    package_id = config.get("package_id", DEFAULT_PACKAGE_ID)
    license_id = config.get("license", DEFAULT_LICENSE)
    abstract = config.get("abstract", DEFAULT_ABSTRACT)
    org = f"<organizationName>{escape(publisher)}</organizationName>"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<eml:eml xmlns:eml="eml://ecoinformatics.org/eml-2.1.1"\n'
        '         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n'
        f'         packageId={_attr(package_id)} system="laubmann-kg" scope="system"\n'
        '         xml:lang="de">\n'
        "  <dataset>\n"
        f"    <title xml:lang=\"en\">{escape(title)}</title>\n"
        "    <creator><individualName><givenName>Alfred</givenName>"
        "<surName>Laubmann</surName></individualName></creator>\n"
        f"    <metadataProvider>{org}</metadataProvider>\n"
        f"    <pubDate>{today.isoformat()}</pubDate>\n"
        "    <language>de</language>\n"
        f"    <abstract><para>{escape(abstract)}</para></abstract>\n"
        f"    {_rights(license_id)}\n"
        f"    {_coverage(result)}\n"
        f"    <contact>{org}</contact>\n"
        f"    {_methods(result)}\n"
        "  </dataset>\n"
        "</eml:eml>\n"
    )


def _attr(value: str) -> str:
    return quoteattr(str(value))


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
    (output_dir / "eml.xml").write_text(build_eml(result, config), encoding="utf-8")

    zip_path = output_dir / config.get("zip_name", DEFAULT_ZIP_NAME)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in [*tables.keys(), "meta.xml", "eml.xml"]:
            archive.write(output_dir / name, arcname=name)

    logger.info("wrote DwC-A to %s (%s)", zip_path, counts)
    return {"dir": str(output_dir), "zip": str(zip_path), "counts": counts,
            "package_id": config.get("package_id", DEFAULT_PACKAGE_ID)}
