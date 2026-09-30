"""Corpus patches for ontology 0.6.0: reviewed entry boundaries, relinked
multimodal regions, and the pipeline/emitter side that reads them."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from rdflib import Literal
from rdflib.namespace import DCTERMS, RDF

ADDONS = Path(__file__).resolve().parents[1] / "HistOrniGraph_addons"
for _p in (ADDONS, ADDONS / "dedup"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import apply_entry_boundaries as aeb  # noqa: E402
import build_multimodal_regions as bmr  # noqa: E402
from laubmann_corpus.boundaries import FIELDS, locate_line  # noqa: E402

from laubmann_kg.extraction.llm_observations import _fold_vocal_behaviour  # noqa: E402
from laubmann_kg.kg.model import Evidence  # noqa: E402
from laubmann_kg.kg.rdf import DATA, LKG, build_graph  # noqa: E402
from laubmann_kg.normalization.vocabularies import split_vocal_behaviour  # noqa: E402
from laubmann_kg.pipeline import build_entry, run_pipeline  # noqa: E402

# One volume, three pages: a detected day, a page whose typed report (numeric
# date) the detector misses, and the volume's register glued onto the last day.
P1 = ("7. April 1917. <u>München</u>.\nWetter trüb. Eine Amsel singt im Garten.\n"
      "Am Nachmittag 3 Stare.")
P2 = ("Noch 2 Buchfinken am Haus.\n"
      "Ismaning, den 14.4.54.\nVom Vkl bis zum Stichrohr 12 Lachmöwen.")
P3 = ("8. April 1917. <u>München</u>.\nRegen. Keine Vögel.\n"
      "<u>Amsel</u>: 1; 3;\n<u>Star</u>: 1;\n<u>Lachmöwe</u>: 2;")


def _page(scan: int, text: str) -> dict:
    return {"volume": 5, "page_id": f"uuid_{scan:04d}_L", "scan": scan, "page_number": "",
            "image": f"uuid_{scan:04d}_L.png",
            "regions": [{"region_uid": f"r_{scan}", "id": "r01", "type": "ParagraphRegion",
                         "reading_order": 1, "page_side": "", "line_count": 3,
                         "crop": "", "text": text, "entry_starts": []}]}


def _corpus(tmp_path: Path) -> tuple[Path, list[dict]]:
    pages = [_page(10, P1), _page(11, P2), _page(12, P3)]
    corpus_dir = tmp_path / "corpus_dedup"
    corpus_dir.mkdir()
    (corpus_dir / "corpus.json").write_text(json.dumps(pages), encoding="utf-8")
    # the "input" entries.csv as apply_dedup would write it (detected headers only)
    entries, _, _ = aeb.regenerate(pages, [], {})
    for i, e in enumerate(entries, 1):          # detector numbering, as apply_dedup writes it
        e["entry_id"] = f"L05-e{i:04d}"
    with (corpus_dir / "entries.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=aeb.ENTRY_COLS, extrasaction="ignore")
        w.writeheader()
        for e in entries:
            w.writerow(e)
    return corpus_dir, entries


def _boundaries(tmp_path: Path) -> Path:
    path = tmp_path / "entry_boundaries.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerow({"action": "start", "volume": 5, "page_id": "uuid_0011_L", "region_id": "r01",
                    "line": "Ismaning, den 14.4.54.", "date_iso": "1954-04-14", "location": "Ismaning",
                    "kind": "correspondence", "confidence": "high", "source": "review"})
        w.writerow({"action": "stop", "volume": 5, "page_id": "uuid_0012_L", "region_id": "r01",
                    "line": "<u>Amsel</u>: 1; 3;", "kind": "register", "source": "review"})
    return path


def test_locate_line_matches_whole_lines_only() -> None:
    assert locate_line("a\nIsmaning, den 14.4.54.\nb", "Ismaning, den 14.4.54.") == 2
    assert locate_line("a Ismaning, den 14.4.54.", "Ismaning, den 14.4.54.") is None


def test_boundaries_split_and_stop_keep_identity(tmp_path) -> None:
    corpus_dir, before = _corpus(tmp_path)
    assert [e["date_raw"] for e in before] == ["7. April 1917", "8. April 1917"]
    out_dir = tmp_path / "patched"
    assert aeb.main(["--corpus-dir", str(corpus_dir), "--boundaries", str(_boundaries(tmp_path)),
                     "--out-dir", str(out_dir)]) == 0
    with (out_dir / "entries.csv").open(newline="", encoding="utf-8") as fh:
        after = list(csv.DictReader(fh))
    assert len(after) == 3
    old = {e["entry_uid"]: e for e in before}
    # detected entries keep uid and id; the report gets the id of the entry before it + "a"
    assert [a["entry_id"] for a in after] == ["L05-e0001", "L05-e0001a", "L05-e0002"]
    assert after[0]["entry_uid"] in old and after[2]["entry_uid"] in old
    report = after[1]
    assert report["entry_uid"] not in old
    assert report["date_norm"] == "1954-04-14" and report["location_raw"] == "Ismaning"
    assert report["boundary_source"] == "review" and report["boundary_kind"] == "correspondence"
    assert report["text_clean"].startswith("Ismaning, den 14.4.54.")
    # the day before now ends before the report but keeps its continuation page
    first = after[0]
    assert "Buchfinken" in first["text_clean"] and "Lachmöwen" not in first["text_clean"]
    assert [r["page_id"] for r in json.loads(first["source_regions"])] == ["uuid_0010_L", "uuid_0011_L"]
    # the register is no longer part of the last day
    last = after[2]
    assert "Regen. Keine Vögel." in last["text_clean"] and "Amsel" not in last["text_clean"]
    summary = json.loads((out_dir / "boundaries_summary.json").read_text())
    assert summary["lost_entries"] == 0 and summary["new_entries"] == 1
    assert summary["boundaries"] == {"start:applied": 1, "stop:applied": 1}
    # corpus.json carries the boundary header and the stop for later stages
    pages = json.loads((out_dir / "corpus.json").read_text())
    assert any(h.get("variant") == "boundary" for p in pages for r in p["regions"] for h in r["entry_starts"])
    assert pages[2]["regions"][0]["entry_stops"]


def test_multimodal_relink_follows_patched_entries(tmp_path) -> None:
    corpus_dir, _ = _corpus(tmp_path)
    out_dir = tmp_path / "patched"
    aeb.main(["--corpus-dir", str(corpus_dir), "--boundaries", str(_boundaries(tmp_path)),
              "--out-dir", str(out_dir)])
    pages = json.loads((out_dir / "corpus.json").read_text())
    with (out_dir / "entries.csv").open(newline="", encoding="utf-8") as fh:
        by_id = {r["entry_id"]: r["entry_uid"] for r in csv.DictReader(fh)}
    regions = [
        # a photo on an image-only page between scan 10 and 11 -> the 7 April day
        {"region_uid": "r_photo", "page_uid": "p_x", "page_id": "uuid_0010_R", "volume": 5, "scan": 10,
         "type_original": "ImageRegion", "description": "A sepia photograph of a pond.", "entry_uid": "e_old"},
        # a map after the report header on page 11 -> the report entry
        {"region_uid": "r_map", "page_uid": "p_y", "page_id": "uuid_0011_L", "volume": 5, "scan": 11,
         "type_original": "ImageRegion", "description": "A hand-drawn map of the reservoir.", "entry_uid": ""},
        # a feather after the register stop -> no entry
        {"region_uid": "r_feather", "page_uid": "p_z", "page_id": "uuid_0012_L", "volume": 5, "scan": 12,
         "type_original": "ObjectRegion", "description": "A feather taped to paper.", "entry_uid": ""},
    ]
    order = {"r_photo": 1, "r_map": 2, "r_feather": 2}
    rows, stats = bmr.build(pages, regions, [], order, {}, {})
    link = {r["region_uid"]: r["entry_uid"] for r in rows}
    assert link == {"r_photo": by_id["L05-e0001"], "r_map": by_id["L05-e0001a"], "r_feather": ""}
    kinds = {r["region_uid"]: r["kind"] for r in rows}
    assert kinds == {"r_photo": "photograph", "r_map": "map", "r_feather": "object"}
    # a duplicate is dropped, a marginal note never becomes a region, an unselected insert neither
    inserts = [{"region_uid": "r_note", "page_uid": "p_y", "page_id": "uuid_0011_L", "volume": 5, "scan": 11,
                "type_original": "MarginaliaRegion", "class": "text", "visible_text": "fig. 1"},
               {"region_uid": "r_clip", "page_uid": "p_y", "page_id": "uuid_0011_L", "volume": 5, "scan": 11,
                "type_original": "ParagraphRegion", "class": "text", "visible_text": "Die Lachmöwe …"},
               {"region_uid": "r_ad", "page_uid": "p_y", "page_id": "uuid_0011_L", "volume": 5, "scan": 11,
                "type_original": "ParagraphRegion", "class": "text", "visible_text": "Vermietungen"}]
    rows, stats = bmr.build(pages, regions, inserts, dict(order, r_clip=3, r_ad=3),
                            {"r_clip": "keep", "r_ad": "drop"}, {"r_map": "r_photo"})
    assert {r["region_uid"] for r in rows} == {"r_photo", "r_feather", "r_clip"}
    assert next(r for r in rows if r["region_uid"] == "r_clip")["kind"] == "text-insert"
    assert stats["insert_marginalia_excluded"] == 1 and stats["duplicate_removed_images-v2"] == 1


def test_pipeline_reads_regions_and_emits_them(tmp_path) -> None:
    corpus_dir, _ = _corpus(tmp_path)
    out_dir = tmp_path / "patched"
    aeb.main(["--corpus-dir", str(corpus_dir), "--boundaries", str(_boundaries(tmp_path)),
              "--out-dir", str(out_dir)])
    pages = json.loads((out_dir / "corpus.json").read_text())
    rows, _ = bmr.build(pages, [{"region_uid": "r_photo", "page_uid": "p_x", "page_id": "uuid_0010_R",
                                 "volume": 5, "scan": 10, "type_original": "ImageRegion",
                                 "description": "A sepia photograph of a pond.", "visible_text": "Teich",
                                 "crop": "regions/uuid_0010_R/r01_ImageRegion.png"}],
                        [], {"r_photo": 1}, {}, {})
    with (out_dir / "multimodal_regions.jsonl").open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    config = {"extraction": {"backend": "offline"}, "qa": {"enabled": False}}
    result = run_pipeline(config, input_dir=out_dir)
    day = next(e for e in result.entries if e.entry_id == "L05-e0001")
    assert [r.page_id for r in day.source_regions] == ["uuid_0010_L", "uuid_0011_L"]
    assert [m.region_uid for m in day.multimodal] == ["r_photo"] and len(result.multimodal) == 1
    graph = build_graph(result)
    region = DATA["region_r_photo"]
    assert (DATA[day.uid], LKG.hasMultimodalRegion, region) in graph
    assert (region, RDF.type, LKG.MultimodalRegion) in graph
    assert graph.value(region, LKG.regionKind) == Literal("photograph")
    assert graph.value(DATA["region_r_11"], DCTERMS.isPartOf) == DATA["page_p_" + pages[1]["page_uid"][2:]]


def test_build_entry_reads_source_regions() -> None:
    entry = build_entry({"entry_uid": "e_1", "entry_id": "L05-e0001", "volume": "5", "page_uid": "p_1",
                         "page_id": "x_L", "region_uid": "r_1", "date_raw": "7. April 1917",
                         "date_norm": "1917-04-07", "text_clean": "t",
                         "source_regions": json.dumps([{"region_uid": "r_1", "page_uid": "p_1", "page_id": "x_L", "scan": 10},
                                                       {"region_uid": "r_2", "page_uid": "p_2", "page_id": "y_L", "scan": 11}])})
    assert [(r.region_uid, r.scan) for r in entry.source_regions] == [("r_1", "10"), ("r_2", "11")]
    assert build_entry({"entry_uid": "e_2", "source_regions": "not json"}).source_regions == []


def test_vocal_behaviour_folds_into_call_type() -> None:
    kept, calls = split_vocal_behaviour(["singend", "lockend verhört", "Warnruf", "badet",
                                         "singend auf der Fichtenspitze", "balzend"])
    assert kept == ["badet", "singend auf der Fichtenspitze", "balzend"]
    assert calls == ["song", "call", "alarm"]
    # an untyped auditory evidence takes the first type; further types are added
    evidence, behaviour = _fold_vocal_behaviour(
        [Evidence("auditory", "Lautäußerung", is_call=True, call_transcription="zick")], ["singt", "ruft"])
    assert [(e.call_type, e.call_transcription) for e in evidence] == [("song", "zick"), ("call", None)]
    assert behaviour == []
    # nothing heard in the behaviour -> evidence untouched, phrase kept
    evidence, behaviour = _fold_vocal_behaviour([], ["kreisend"])
    assert evidence == [] and behaviour == ["kreisend"]


def test_masked_regions_leave_uids_and_drop_header_only_entries(tmp_path) -> None:
    """A masked region is blanked out of the entry text (offsets unchanged, so
    uids stay); an entry whose header sits in a masked region is dropped and a
    boundary start inside one is not applied."""
    corpus_dir, before = _corpus(tmp_path)
    mask = tmp_path / "masked_regions.csv"
    mask.write_text("region_uid,reason\nr_11,unreliable-transcription\n", encoding="utf-8")
    out_dir = tmp_path / "patched"
    assert aeb.main(["--corpus-dir", str(corpus_dir), "--boundaries", str(_boundaries(tmp_path)),
                     "--mask", str(mask), "--out-dir", str(out_dir)]) == 0
    with (out_dir / "entries.csv").open(newline="", encoding="utf-8") as fh:
        after = list(csv.DictReader(fh))
    assert [a["entry_uid"] for a in after] == [e["entry_uid"] for e in before]   # the report start was masked
    first = after[0]
    assert "Buchfinken" not in first["text_clean"] and "Lachmöwen" not in first["text_clean"]
    assert [r["page_id"] for r in json.loads(first["source_regions"])] == ["uuid_0010_L"]
    summary = json.loads((out_dir / "boundaries_summary.json").read_text())
    assert summary["boundaries"]["start:masked"] == 1 and summary["masked_regions"] == 1
    # corpus.json keeps the transcription and marks the region
    page = json.loads((out_dir / "corpus.json").read_text())[1]
    assert page["regions"][0]["masked"] == "unreliable-transcription" and "Buchfinken" in page["regions"][0]["text"]
    # a detected header inside a masked region: the entry is dropped, nothing else moves
    mask.write_text("region_uid,reason\nr_12,unreliable-transcription\n", encoding="utf-8")
    out2 = tmp_path / "patched2"
    assert aeb.main(["--corpus-dir", str(corpus_dir), "--boundaries", str(_boundaries(tmp_path)),
                     "--mask", str(mask), "--out-dir", str(out2)]) == 0
    summary = json.loads((out2 / "boundaries_summary.json").read_text())
    assert summary["dropped_masked_header_entry_ids"] == ["L05-e0002"] and summary["lost_entries"] == 0


def test_multimedia_rows_only_for_event_entries() -> None:
    """A region of an undated entry (no DwC event) gets no multimedia row."""
    from laubmann_kg.dwca.multimedia import build_multimedia
    from laubmann_kg.kg.model import DiaryEntry, MultimodalRegion
    from laubmann_kg.pipeline import ExtractionResult
    dated = DiaryEntry("e_1", "L05-e0001", 5, "p_1", "x_L", "r_1", "10", "1917-04-07", None, None, "t")
    undated = DiaryEntry("e_2", "L05-e0002", 5, "p_1", "x_L", "r_2", "10", None, "71. Juni 1955", None, "t")
    regions = [MultimodalRegion("r_a", "p_1", "x_L", 5, "10", "e_1", "photograph", crop="a.png"),
               MultimodalRegion("r_b", "p_1", "x_L", 5, "10", "e_2", "map", crop="b.png")]
    rows = build_multimedia(ExtractionResult(entries=[dated, undated], multimodal=regions))
    assert [r["identifier"] for r in rows] == ["a.png"]
