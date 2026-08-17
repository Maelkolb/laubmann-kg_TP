"""DwC-A v2: model-provided occurrence detail, eMoF, meta.xml/EML pieces."""

import csv
import datetime as dt
import json
from pathlib import Path
from xml.etree import ElementTree

import pytest

from laubmann_kg.dwca.archive import build_archive, build_eml
from laubmann_kg.dwca.event import build_events
from laubmann_kg.dwca.measurement_or_fact import (
    ROW_TYPE as EMOF_ROW_TYPE,
    build_measurements,
    concept_iri,
    scheme_iri,
)
from laubmann_kg.dwca.meta_xml import DWC, ROW_TYPES, FileSpec, build_meta_xml
from laubmann_kg.dwca.multimedia import build_multimedia
from laubmann_kg.dwca.occurrence import build_occurrences
from laubmann_kg.dwca.validate import validate_archive
from laubmann_kg.kg.model import (
    Behaviour,
    DiaryEntry,
    Evidence,
    Habitat,
    Observation,
    Place,
    Taxon,
    WeatherReport,
)
from laubmann_kg.pipeline import ExtractionResult

DWCA_NS = "{http://rs.tdwg.org/dwc/text/}"
LKG = "https://lkg.example.org/ontology#"


def _tsv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t", quoting=csv.QUOTE_NONE))


def _entry(uid="e_v2_0001", date="1921-05-03", date_end=None,
           place=Place("Erlangen", "Erlangen", lat=49.5897, long=11.0040, kind="settlement"),
           location_raw="Erlangen (Regnitzgrund)") -> DiaryEntry:
    return DiaryEntry(
        entry_uid=uid, entry_id="L05-e0042", volume=5, page_uid="p5", page_id="pid5",
        region_uid=None, scan="12", entry_date=date, verbatim_event_date="3. Mai 1921",
        location_raw=location_raw, text_clean="Text.\tMit Tab.", place=place,
        entry_date_end=date_end,
    )


def _rich_result() -> ExtractionResult:
    """One multi-day entry with: a range-counted, sexed, breeding, moving bird
    at its own locality/date/time; an absence record (count 0); a genus-level
    identification with hedge; a non-bird; an LLM/GBIF-linked species."""
    entry = _entry(date_end="1921-05-04")
    entry.weather = WeatherReport(verbatim="heiter, warm", sky="clear")
    own_place = Place("Dechsendorfer Weiher", "Dechsendorfer Weiher",
                      lat=49.6217, long=10.9581, kind="locality")
    kiebitz = Observation(
        entry_uid=entry.entry_uid,
        taxon=Taxon("Kiebitz", "Vanellus vanellus", rank="species", is_bird=True,
                    gbif_key=2480242, gbif_match_type="EXACT"),
        verbatim_notes="3-4 Kiebitze, ♂♂, balzend über der Wiese, ziehen nach NO",
        index=0, place=own_place, locality=own_place, individual_count=None,
        count_min=3, count_max=4, count_qualifier="approximate", sex="male",
        life_stage="adult", breeding_evidence="probable", movement_kind="migrating",
        flight_direction="NO", event_date="1921-05-04", event_time="06:30",
        habitat=Habitat("Feuchtwiese"),
        evidence=[Evidence("visual", "gesehen"),
                  Evidence("auditory", "Balzruf", is_call=True, call_type="call")],
        behaviour=[Behaviour("Balz", reproductive_condition="breeding"),
                   Behaviour("Zug")],
    )
    absent = Observation(
        entry_uid=entry.entry_uid,
        taxon=Taxon("Wachtelkönig", "Crex crex", rank="species", is_bird=True),
        verbatim_notes="Wachtelkönig heuer nicht gehört", index=1,
        place=entry.place, individual_count=0, occurrence_status="absent",
        evidence=[Evidence("auditory", "nicht gehört", occurrence_status="absent")],
    )
    genus = Observation(
        entry_uid=entry.entry_uid,
        taxon=Taxon("Uferschnepfe?", "Limosa", rank="genus", is_bird=True),
        verbatim_notes="wohl Limosa, zu weit", index=2, place=entry.place,
        identification_qualifier="wohl", individual_count=1, count_qualifier="exact",
    )
    mammal = Observation(
        entry_uid=entry.entry_uid,
        taxon=Taxon("Reh", "Capreolus capreolus", rank="species", is_bird=False),
        verbatim_notes="2 Rehe am Waldrand", index=3, place=entry.place,
        individual_count=2, count_qualifier="exact", vitality="dead",
        record_type="third-party-report",
    )
    unnamed = Observation(
        entry_uid=entry.entry_uid, taxon=Taxon("Möwen", None, rank="group"),
        verbatim_notes="viele Möwen", index=4, place=entry.place,
        count_qualifier="plural-unspecified",
    )
    plain = Observation(
        entry_uid=entry.entry_uid, taxon=Taxon("Amsel"),
        verbatim_notes="Amsel singt", index=5, place=entry.place,
    )
    entry.observations = [kiebitz, absent, genus, mammal, unnamed, plain]
    result = ExtractionResult(
        entries=[entry],
        provenance={"backend": "llm", "provider": "google", "model": "gemini-3.5-flash",
                    "prompt": "observation_extraction", "prompt_sha256": "abc123",
                    "temperature": 0.0, "thinking_level": "low",
                    "started_at": "2026-08-17T10:00:00+00:00",
                    "method": "LLM extraction from diary text (gemini-3.5-flash)"},
        multimodal=[{"entry_uid": entry.entry_uid, "crop": "crops/L05_p12_r1.png",
                     "region_type": "sketch", "description": "Federzeichnung Kiebitz",
                     "visible_text": "Kiebitz\n3.V.21"},
                    {"entry_uid": entry.entry_uid, "crop": "crops/L05_p12_r2.png",
                     "region_type": "table", "description": "", "visible_text": ""}],
    )
    result.places = {entry.place.uid: entry.place, own_place.uid: own_place}
    return result


# --- event core --------------------------------------------------------------

def test_event_row_uses_entry_place_and_interval() -> None:
    result = _rich_result()
    rows = build_events(result)
    assert len(rows) == 1
    row = rows[0]
    assert row["eventDate"] == "1921-05-03/1921-05-04"          # multi-day interval
    assert row["locality"] == "Erlangen"                         # entry.place.name
    assert row["verbatimLocality"] == "Erlangen (Regnitzgrund)"  # header as written
    assert row["decimalLatitude"] == "49.5897" and row["decimalLongitude"] == "11.0040"
    assert row["geodeticDatum"] == "WGS84"
    assert row["eventRemarks"] == "heiter, warm"
    assert json.loads(row["dynamicProperties"]) == {"skyCondition": "clear"}
    assert "\t" not in row["fieldNotes"]


def test_event_row_without_place_or_coordinates() -> None:
    no_place = _entry(uid="e_v2_np", place=None)
    no_coords = _entry(uid="e_v2_nc", place=Place("Irgendwo", None, kind="unknown"),
                       location_raw="Irgendwo")
    undated = _entry(uid="e_v2_nd", date=None)
    rows = {r["eventID"]: r for r in build_events(ExtractionResult(
        entries=[no_place, no_coords, undated]))}
    assert set(rows) == {"e_v2_np", "e_v2_nc"}                  # undated entries skipped
    assert rows["e_v2_np"]["locality"] == ""
    assert rows["e_v2_np"]["verbatimLocality"] == "Erlangen (Regnitzgrund)"
    assert rows["e_v2_np"]["geodeticDatum"] == ""
    assert rows["e_v2_nc"]["locality"] == "Irgendwo"
    assert rows["e_v2_nc"]["decimalLatitude"] == "" and rows["e_v2_nc"]["geodeticDatum"] == ""
    assert rows["e_v2_nc"]["eventDate"] == "1921-05-03"         # single day: no slash


# --- occurrence extension ----------------------------------------------------

def test_occurrence_columns_from_model_detail() -> None:
    result = _rich_result()
    rows = {r["vernacularName"]: r for r in build_occurrences(result, {
        result.entries[0].entry_uid: ["crops/L05_p12_r1.png", "crops/L05_p12_r2.png"]})}
    assert len(rows) == 6

    k = rows["Kiebitz"]
    assert k["kingdom"] == "Animalia" and k["class"] == "Aves"
    assert k["scientificName"] == "Vanellus vanellus" and k["taxonRank"] == "species"
    assert k["taxonID"] == "https://www.gbif.org/species/2480242"
    assert k["individualCount"] == ""                              # None, range instead
    assert k["organismQuantity"] == "3-4"
    assert k["organismQuantityType"] == "individuals (range)"
    assert k["occurrenceStatus"] == "present"
    assert k["sex"] == "male" and k["lifeStage"] == "adult"
    assert k["reproductiveCondition"] == "breeding"                # from breeding_evidence
    assert k["vitality"] == ""
    assert k["behavior"] == "Balz; Zug"
    assert k["identificationQualifier"] == "" and k["identificationRemarks"] == ""
    assert k["locality"] == "Dechsendorfer Weiher"                 # own place
    assert k["verbatimLocality"] == "Dechsendorfer Weiher"
    assert k["eventDate"] == "1921-05-04" and k["eventTime"] == "06:30"
    assert k["habitat"] == "Feuchtwiese"
    assert k["recordedBy"] == "Alfred Laubmann"
    assert k["associatedMedia"] == "crops/L05_p12_r1.png;crops/L05_p12_r2.png"
    assert json.loads(k["dynamicProperties"]) == {
        "movementKind": "migrating", "flightDirection": "NO",
        "countMin": 3, "countMax": 4, "breedingEvidence": "probable",
        "recordType": "field-observation"}

    a = rows["Wachtelkönig"]
    assert a["occurrenceStatus"] == "absent"
    assert a["individualCount"] == "0"                             # 0 is a value
    assert a["organismQuantity"] == ""
    assert a["basisOfRecord"] == "HumanObservation"

    g = rows["Uferschnepfe?"]
    assert g["scientificName"] == "Limosa" and g["taxonRank"] == "genus"
    assert g["identificationQualifier"] == "wohl"
    assert g["identificationRemarks"] == "Bestimmung auf genus-Niveau"
    assert g["individualCount"] == "1"

    m = rows["Reh"]
    assert m["kingdom"] == "" and m["class"] == ""                 # is_bird False
    assert m["vitality"] == "dead"
    assert m["recordedBy"] == ""                                   # unattributed report
    assert json.loads(m["dynamicProperties"]) == {"recordType": "third-party-report"}

    u = rows["Möwen"]
    assert u["identificationRemarks"] == "Bestimmung auf group-Niveau"
    assert u["taxonRank"] == "group" and u["scientificName"] == ""

    p = rows["Amsel"]
    assert p["identificationRemarks"] == "Art nicht sicher bestimmt; nur Trivialname"
    assert p["kingdom"] == "Animalia" and p["class"] == ""         # is_bird None
    assert p["locality"] == "Erlangen"                             # effective = entry place
    assert p["verbatimLocality"] == ""                             # no own locality
    assert p["eventDate"] == "1921-05-03/1921-05-04"               # inherits event interval
    assert p["taxonRank"] == ""


def test_occurrence_reproductive_condition_falls_back_to_behaviour() -> None:
    entry = _entry()
    entry.observations = [Observation(
        entry_uid=entry.entry_uid, taxon=Taxon("Storch", "Ciconia ciconia"),
        verbatim_notes="Nest besetzt", index=0,
        behaviour=[Behaviour("Brüten / besetztes Nest", reproductive_condition="breeding")])]
    row = build_occurrences(ExtractionResult(entries=[entry]))[0]
    assert row["reproductiveCondition"] == "breeding"
    assert row["behavior"] == "Brüten / besetztes Nest"


# --- eMoF extension ----------------------------------------------------------

def test_emof_rows_ids_and_method() -> None:
    result = _rich_result()
    rows = build_measurements(result)
    kiebitz_uid = result.entries[0].observations[0].uid
    by_id = {r["measurementID"]: r for r in rows}
    assert len(by_id) == len(rows)                                 # unique measurementID
    assert all(r["eventID"] == "e_v2_0001" for r in rows)
    assert all(r["measurementMethod"] ==
               "LLM extraction from diary text (gemini-3.5-flash)" for r in rows)

    kiebitz = [r for r in rows if r["occurrenceID"] == kiebitz_uid]
    types = [(r["measurementType"], r["measurementValue"]) for r in kiebitz]
    assert types == [("evidenceType", "visual"), ("evidenceType", "auditory"),
                     ("callType", "call"), ("countQualifier", "approximate"),
                     ("breedingEvidence", "probable"), ("movementKind", "migrating")]
    assert [r["measurementID"] for r in kiebitz][:3] == [
        f"{kiebitz_uid}:evidenceType:0", f"{kiebitz_uid}:evidenceType:1",
        f"{kiebitz_uid}:callType:0"]
    ev = by_id[f"{kiebitz_uid}:evidenceType:1"]
    assert ev["measurementTypeID"] == LKG + "evidenceKindScheme"
    assert ev["measurementValueID"] == LKG + "evidence_auditory"
    assert by_id[f"{kiebitz_uid}:callType:0"]["measurementTypeID"] == LKG + "callTypeScheme"
    assert by_id[f"{kiebitz_uid}:callType:0"]["measurementValueID"] == LKG + "call_call"
    assert by_id[f"{kiebitz_uid}:breedingEvidence:0"]["measurementValueID"] == LKG + "breeding_probable"
    assert by_id[f"{kiebitz_uid}:breedingEvidence:0"]["measurementTypeID"] == LKG + "breedingEvidenceScheme"
    assert by_id[f"{kiebitz_uid}:movementKind:0"]["measurementValueID"] == LKG + "movement_migrating"
    assert by_id[f"{kiebitz_uid}:movementKind:0"]["measurementTypeID"] == LKG + "movementKindScheme"

    # hyphenated values -> underscore concept local names
    moewen_uid = result.entries[0].observations[4].uid
    assert by_id[f"{moewen_uid}:countQualifier:0"]["measurementValueID"] == \
        LKG + "count_plural_unspecified"
    assert concept_iri("movementKind", "passing-over") == LKG + "movement_passing_over"
    assert scheme_iri("countQualifier") == LKG + "countQualifierScheme"

    # default method when provenance is absent
    bare = ExtractionResult(entries=result.entries)
    assert build_measurements(bare)[0]["measurementMethod"] == "extraction from diary text"


# --- multimedia --------------------------------------------------------------

def test_multimedia_description_folds_visible_text() -> None:
    rows = build_multimedia(_rich_result())
    assert [r["identifier"] for r in rows] == ["crops/L05_p12_r1.png", "crops/L05_p12_r2.png"]
    assert rows[0]["description"] == "Federzeichnung Kiebitz — Text: Kiebitz 3.V.21"
    assert rows[1]["description"] == ""
    assert "subjectPart" not in rows[0]


# --- meta.xml ----------------------------------------------------------------

def test_meta_xml_core_declares_eventid_and_emof_rowtype() -> None:
    xml = build_meta_xml(
        FileSpec("event", "event.txt", ["eventID", "eventDate"]),
        [FileSpec("measurement_or_fact", "measurementorfact.txt",
                  ["eventID", "occurrenceID", "measurementTypeID"]),
         FileSpec("multimedia", "multimedia.txt", ["eventID", "identifier"])])
    root = ElementTree.fromstring(xml)
    core = root.find(DWCA_NS + "core")
    assert core.get("rowType") == DWC + "Event"
    assert core.find(DWCA_NS + "id").get("index") == "0"
    core_fields = [(f.get("index"), f.get("term")) for f in core.findall(DWCA_NS + "field")]
    assert core_fields[0] == ("0", DWC + "eventID")                # id column also a term
    assert core_fields[1] == ("1", DWC + "eventDate")

    exts = {e.get("rowType"): e for e in root.findall(DWCA_NS + "extension")}
    emof = exts[EMOF_ROW_TYPE]
    assert EMOF_ROW_TYPE == "http://rs.iobis.org/obis/terms/ExtendedMeasurementOrFact"
    assert ROW_TYPES["measurement_or_fact"] == EMOF_ROW_TYPE
    assert emof.find(DWCA_NS + "coreid").get("index") == "0"
    emof_fields = {f.get("index"): f.get("term") for f in emof.findall(DWCA_NS + "field")}
    assert "0" not in emof_fields                                  # coreid only
    assert emof_fields["1"] == DWC + "occurrenceID"
    assert emof_fields["2"] == "http://rs.iobis.org/obis/terms/measurementTypeID"
    mm = exts["http://rs.gbif.org/terms/1.0/Multimedia"]
    assert [f.get("term") for f in mm.findall(DWCA_NS + "field")] == [
        "http://purl.org/dc/terms/identifier"]
    assert "ac/terms" not in xml


# --- EML ---------------------------------------------------------------------

def test_eml_metadata_pieces() -> None:
    result = _rich_result()
    xml = build_eml(result, {"publisher": "Laubmann KG Project", "license": "CC-BY-4.0"},
                    today=dt.date(2026, 8, 17))
    root = ElementTree.fromstring(xml)
    assert root.get("packageId") == "laubmann-kg-full"
    ds = root.find("dataset")
    assert ds.find("title").text == "Laubmann ornithological field diaries 1917–1965 — observations"
    assert ds.find("pubDate").text == "2026-08-17"
    assert ds.find("language").text == "de"
    assert ds.find("abstract/para").text.startswith("Ornithological observations")
    assert ds.find("metadataProvider/organizationName").text == "Laubmann KG Project"
    assert ds.find("contact/organizationName").text == "Laubmann KG Project"
    ulink = ds.find("intellectualRights/para/ulink")
    assert ulink.get("url") == "https://creativecommons.org/licenses/by/4.0/"
    assert ulink.find("citetitle").text == "Creative Commons Attribution 4.0"
    cov = ds.find("coverage")
    assert cov.find("temporalCoverage/rangeOfDates/beginDate/calendarDate").text == "1921-05-03"
    assert cov.find("temporalCoverage/rangeOfDates/endDate/calendarDate").text == "1921-05-04"
    bbox = cov.find("geographicCoverage/boundingCoordinates")
    assert bbox.find("westBoundingCoordinate").text == "10.9581"
    assert bbox.find("eastBoundingCoordinate").text == "11.0040"
    assert bbox.find("southBoundingCoordinate").text == "49.5897"
    assert bbox.find("northBoundingCoordinate").text == "49.6217"
    tc = cov.find("taxonomicCoverage/taxonomicClassification")
    assert tc.find("taxonRankName").text == "class" and tc.find("taxonRankValue").text == "Aves"
    method = ds.find("methods/methodStep/description/para").text
    assert method.startswith("LLM extraction from diary text (gemini-3.5-flash)")
    assert "gemini-3.5-flash" in method and "abc123" in method
    # dataset element order as EML 2.1.1 requires
    tags = [child.tag for child in ds]
    assert tags == ["title", "creator", "metadataProvider", "pubDate", "language",
                    "abstract", "intellectualRights", "coverage", "contact", "methods"]

    # configurable title/packageId, other license, no coordinates -> no bbox
    bare = ExtractionResult(entries=[_entry(place=None)])
    xml2 = build_eml(bare, {"title": "Probe & Test", "package_id": "laubmann-kg-sample",
                            "license": "All rights reserved"})
    root2 = ElementTree.fromstring(xml2)
    assert root2.get("packageId") == "laubmann-kg-sample"
    assert root2.find("dataset/title").text == "Probe & Test"
    assert root2.find("dataset/intellectualRights/para").text == "All rights reserved"
    assert root2.find("dataset/coverage/geographicCoverage") is None
    assert root2.find("dataset/coverage/temporalCoverage") is not None


# --- whole archive + validator -----------------------------------------------

def test_rich_archive_roundtrip_and_validation(tmp_path: Path) -> None:
    result = _rich_result()
    dwca_dir = tmp_path / "dwca"
    summary = build_archive(result, dwca_dir, {"package_id": "laubmann-kg-test",
                                               "zip_name": "test_dwca.zip"})
    # eMoF: Kiebitz 6 (2 evidence + call + count + breeding + movement),
    # Wachtelkönig 1 (evidence), Limosa 1, Reh 1, Möwen 1 (count qualifiers), Amsel 0
    assert summary["counts"] == {"event.txt": 1, "occurrence.txt": 6,
                                 "measurementorfact.txt": 10, "multimedia.txt": 2}
    assert summary["package_id"] == "laubmann-kg-test"
    assert Path(summary["zip"]).name == "test_dwca.zip"
    assert validate_archive(dwca_dir) == []

    occ = _tsv(dwca_dir / "occurrence.txt")
    absent = [r for r in occ if r["occurrenceStatus"] == "absent"]
    assert len(absent) == 1 and absent[0]["individualCount"] == "0"
    ranged = [r for r in occ if r["organismQuantity"]]
    assert [r["organismQuantity"] for r in ranged] == ["3-4"]
    for row in occ:
        for value in row.values():
            assert "\t" not in value and "\n" not in value
    mof = _tsv(dwca_dir / "measurementorfact.txt")
    assert {r["occurrenceID"] for r in mof} <= {r["occurrenceID"] for r in occ}
    ElementTree.parse(dwca_dir / "eml.xml")


def test_validator_flags_structural_problems(tmp_path: Path) -> None:
    result = _rich_result()
    dwca_dir = tmp_path / "dwca"
    build_archive(result, dwca_dir)
    assert validate_archive(dwca_dir) == []

    # individualCount 0 on a present record; a bad occurrenceStatus
    occ_path = dwca_dir / "occurrence.txt"
    lines = occ_path.read_text(encoding="utf-8").split("\n")
    header = lines[0].split("\t")
    status_i, count_i = header.index("occurrenceStatus"), header.index("individualCount")
    cells = lines[1].split("\t")
    cells[status_i], cells[count_i] = "present", "0"
    lines[1] = "\t".join(cells)
    cells2 = lines[2].split("\t")
    cells2[status_i] = "maybe"
    lines[2] = "\t".join(cells2)
    occ_path.write_text("\n".join(lines), encoding="utf-8")
    problems = validate_archive(dwca_dir)
    assert any("individualCount 0" in p for p in problems)
    assert any("occurrenceStatus" in p for p in problems)

    # dangling occurrenceID in the eMoF
    build_archive(result, dwca_dir)
    mof_path = dwca_dir / "measurementorfact.txt"
    text = mof_path.read_text(encoding="utf-8").replace(
        result.entries[0].observations[0].uid, "obs_nonexistent")
    mof_path.write_text(text, encoding="utf-8")
    assert any("occurrenceID(s) not present" in p for p in validate_archive(dwca_dir))

    # meta.xml without the eMoF extension / eventID field
    build_archive(result, dwca_dir)
    meta = dwca_dir / "meta.xml"
    meta.write_text(meta.read_text(encoding="utf-8").replace(
        EMOF_ROW_TYPE, DWC + "MeasurementOrFact").replace(
        f'<field index="0" term="{DWC}eventID"/>\n', ""), encoding="utf-8")
    problems = validate_archive(dwca_dir)
    assert any("ExtendedMeasurementOrFact" in p for p in problems)
    assert any("eventID" in p for p in problems)


@pytest.mark.parametrize("license_id,expect_link", [
    ("CC-BY-4.0", True), ("CC0-1.0", True), ("proprietary", False)])
def test_eml_license_variants(license_id: str, expect_link: bool) -> None:
    xml = build_eml(ExtractionResult(entries=[_entry()]), {"license": license_id})
    root = ElementTree.fromstring(xml)
    ulink = root.find("dataset/intellectualRights/para/ulink")
    assert (ulink is not None) is expect_link
