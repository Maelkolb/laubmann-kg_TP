import csv
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from laubmann_kg.dwca import export
from laubmann_kg.dwca.validate import validate_archive


def _tsv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def test_dwca_export_produces_valid_archive(sample_config, tmp_path: Path) -> None:
    summary = export(sample_config, None, tmp_path, validate=True)
    assert summary["valid"] is True
    assert summary["problems"] == []

    dwca_dir = tmp_path / "dwca"
    for name in ("meta.xml", "event.txt", "occurrence.txt",
                 "measurementorfact.txt", "multimedia.txt", "eml.xml"):
        assert (dwca_dir / name).exists()

    ElementTree.parse(dwca_dir / "meta.xml")  # well-formed
    assert validate_archive(dwca_dir) == []


def test_occurrence_event_join_integrity(sample_config, tmp_path: Path) -> None:
    export(sample_config, None, tmp_path, validate=False)
    dwca_dir = tmp_path / "dwca"
    event_ids = {r["eventID"] for r in _tsv(dwca_dir / "event.txt")}
    occ = _tsv(dwca_dir / "occurrence.txt")
    assert occ, "expected at least one occurrence"
    assert all(r["eventID"] in event_ids for r in occ)
    assert len({r["occurrenceID"] for r in occ}) == len(occ)


def test_archive_zip_contains_all_members(sample_config, tmp_path: Path) -> None:
    summary = export(sample_config, None, tmp_path, validate=False)
    with ZipFile(summary["zip"]) as archive:
        names = set(archive.namelist())
    assert {"meta.xml", "event.txt", "occurrence.txt", "multimedia.txt",
            "measurementorfact.txt", "eml.xml"} <= names
