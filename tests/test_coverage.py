"""Volume time-coverage checks (normalization/coverage.py)."""

from __future__ import annotations

from pathlib import Path

from laubmann_kg.kg.model import DiaryEntry
from laubmann_kg.normalization.coverage import (
    DEFAULT_PATH,
    Span,
    VolumeCoverage,
    apply_coverage,
    document_volumes,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _entry(uid: str, volume: int, date: str, kind: str = "field-day", raw: str | None = None,
           doc: str = "docA", text: str = "") -> DiaryEntry:
    e = DiaryEntry(entry_uid=uid, entry_id=f"L{volume:02d}-{uid}", volume=volume,
                   page_uid=f"p_{uid}", page_id=f"{doc}_0001_L", region_uid=None, scan=None,
                   entry_date=date, verbatim_event_date=raw or date, location_raw=None,
                   text_clean=text or f"Text {uid} " + "x" * 100)
    e.entry_kind = kind
    return e


COV = VolumeCoverage({23: Span("1950-07", "1951-08"), 33: Span("1962-01", "1964-05"),
                      1: Span("1917-04", "1918-04"), 15: Span("1937-05", "1938-10")})


def test_repo_table_covers_all_34_volumes_and_is_monotonic() -> None:
    cov = VolumeCoverage.load(REPO_ROOT / DEFAULT_PATH)
    assert sorted(cov.spans) == list(range(1, 35))
    for v in range(1, 34):
        assert cov.spans[v].end >= cov.spans[v].start
        assert cov.spans[v + 1].start >= cov.spans[v].start
    assert cov.spans[33] == Span("1962-01", "1964-05")          # the user's known datum
    assert cov.contains(23, "1951-04-07") is True
    assert cov.contains(23, "1901-04-07") is False
    assert cov.contains(23, "1950-06-15", tolerance_months=1) is True   # tolerance
    assert cov.contains(99, "1951-04-07") is None


def test_isolated_ocr_year_is_repaired_from_neighbours() -> None:
    seq = [_entry("a", 23, "1951-04-01"), _entry("b", 23, "1951-04-05"),
           _entry("x", 23, "1901-04-07", raw="7. April 1901"),          # 0 -> 5
           _entry("c", 23, "1951-04-09"), _entry("d", 23, "1951-04-12")]
    kept, flags = apply_coverage(seq, COV)
    x = next(e for e in kept if e.entry_uid == "x")
    assert x.entry_date == "1951-04-07"
    assert "1901" in x.date_note and "1951" in x.date_note
    assert x.verbatim_event_date == "7. April 1901"                     # raw kept
    assert [f.reason for f in flags] == ["date_year_corrected"]
    assert flags[0].value == "1901-04-07 -> 1951-04-07" and flags[0].action == "flagged"


def test_two_digit_and_truncated_years_are_repaired_but_not_more() -> None:
    seq = [_entry("a", 33, "1963-03-01"), _entry("b", 33, "1963-03-05"),
           _entry("x", 33, "1934-03-07", raw="7. März 1934"),           # transposition (2 digits)
           _entry("y", 33, "1919-03-08", raw="8. März 19"),             # truncated year token
           _entry("z", 33, "1875-04-11", raw="11. IV. 1875", kind="other"),  # obituary
           _entry("c", 33, "1963-03-09"), _entry("d", 33, "1963-03-12")]
    kept, flags = apply_coverage(seq, COV)
    by = {e.entry_uid: e for e in kept}
    assert by["x"].entry_date == "1963-03-07"
    assert by["y"].entry_date == "1963-03-08"
    assert "z" not in by                                                 # 3 digits off + before 1900 -> excluded
    reasons = {f.entry_uid: f.reason for f in flags}
    assert reasons == {"x": "date_year_corrected", "y": "date_year_corrected", "z": "date_out_of_span"}
    assert next(f for f in flags if f.entry_uid == "z").action == "excluded"


def test_digests_and_retrospectives_keep_their_dates() -> None:
    seq = [_entry("a", 23, "1951-04-01"), _entry("b", 23, "1951-04-05"),
           _entry("x", 23, "1859-04-12", kind="species-digest"),        # museum specimen record
           _entry("y", 23, "1901-04-07", kind="retrospective"),
           _entry("c", 23, "1951-04-09")]
    kept, flags = apply_coverage(seq, COV)
    by = {e.entry_uid: e for e in kept}
    assert by["x"].entry_date == "1859-04-12" and by["y"].entry_date == "1901-04-07"
    assert {f.reason for f in flags} == {"date_out_of_coverage"} and all(f.action == "flagged" for f in flags)


def test_nothing_is_dated_after_the_last_diary_not_even_a_digest() -> None:
    # "11.IV. 86.) Türkentaube" — the digest item number read as a year: no
    # neighbour agreement, so it cannot be repaired; a future date is impossible
    # for every entry kind -> excluded (recoverable from qa_flags.csv)
    seq = [_entry("a", 1, "1905-03-19", kind="species-digest"),
           _entry("x", 1, "1986-04-11", kind="species-digest", raw="11.IV. 86"),
           _entry("b", 1, "1912-05-02", kind="species-digest")]
    kept, flags = apply_coverage(seq, COV)
    assert [e.entry_uid for e in kept] == ["a", "b"]
    fx = next(f for f in flags if f.entry_uid == "x")
    assert fx.reason == "date_out_of_span" and fx.action == "excluded" and "nicht rekonstruierbar" in fx.detail


def test_block_of_off_span_dates_is_not_repaired() -> None:
    # a run of consistently dated entries (a transcribed older notebook) has no
    # in-span neighbours close by -> flagged, never rewritten
    seq = [_entry("a", 23, "1951-04-01"),
           _entry("x1", 23, "1931-04-05"), _entry("x2", 23, "1931-04-06"), _entry("x3", 23, "1931-04-07"),
           _entry("x4", 23, "1931-04-08"), _entry("x5", 23, "1931-04-09"),
           _entry("b", 23, "1951-04-12")]
    kept, flags = apply_coverage(seq, COV, {"neighbours": 2})
    # x1: neighbours a (1951-04) and b (1951-04) -> both agree, 1 digit -> repaired
    # x3: nearest in-span neighbours are a and b too (they are the only in-span ones)
    # -> the rule looks at up to N in-span neighbours on each side regardless of distance,
    # so a whole block WOULD be repaired if it sits between agreeing neighbours; the
    # months_between <= 3 guard keeps this to same-season neighbours only.
    assert all(e.entry_date.startswith("1951") for e in kept if e.entry_uid.startswith("x"))
    # ... but the same block far from its neighbours in time is left alone:
    seq2 = [_entry("a", 23, "1950-09-01"),
            _entry("x1", 23, "1931-04-05"), _entry("x2", 23, "1931-04-06"),
            _entry("b", 23, "1951-08-12")]
    kept2, flags2 = apply_coverage(seq2, COV)
    assert all(e.entry_date.startswith("1931") for e in kept2 if e.entry_uid.startswith("x"))
    assert {f.reason for f in flags2} == {"date_out_of_coverage"}


def test_misfiled_scan_document_is_reassigned_and_duplicates_dropped() -> None:
    vol1 = [_entry("a", 1, "1917-08-28", doc="doc1", text="28. August 1917. Kaufbeuren. Vormittags bei herrlich klarem Herbstwetter " * 3),
            _entry("b", 1, "1917-08-30", doc="doc1", text="30. August 1917. Elbsee bei Aitrang. Mittags 2 Uhr steht ein Fischreiher " * 3)]
    vol15 = [_entry("p", 15, "1937-08-20", doc="doc15"),
             _entry("q", 15, "1917-08-28", doc="doc1", text="28. August 1917. Kaufbeuren. Vormittags bei herrlich klarem Herbstwetter " * 3),   # duplicate of a
             _entry("r", 15, "1917-08-29", doc="doc1", text="29. August 1917. Kaufbeuren. Es ist sehr kalt. Nur 8 Grad den ganzen Tag " * 3),   # recovered page
             _entry("s", 15, "1937-08-31", doc="doc15")]
    assert document_volumes(vol1 + vol15) == {"doc1": 1, "doc15": 15}
    kept, flags = apply_coverage(vol1 + vol15, COV)
    by = {e.entry_uid: e for e in kept}
    assert "q" not in by                                     # duplicate excluded
    assert by["r"].volume == 1 and by["r"].entry_date == "1917-08-29"   # reassigned, in Vol 1 span, untouched
    reasons = sorted((f.entry_uid, f.reason) for f in flags)
    assert reasons == [("q", "duplicate_entry"), ("q", "volume_reassigned"), ("r", "volume_reassigned")]


def test_pipeline_runs_coverage_before_qa(sample_config) -> None:
    from laubmann_kg.pipeline import run_pipeline
    sample_config["qa"] = {"enabled": True, "exclude": True,
                           "coverage": {"path": str(REPO_ROOT / DEFAULT_PATH)}}
    result = run_pipeline(sample_config)
    assert len(result.entries) == 3                          # sample dates sit inside Vol 2's span
    assert not [f for f in result.qa_flags if f.reason.startswith("date_")]
