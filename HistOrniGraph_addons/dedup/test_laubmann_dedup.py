#!/usr/bin/env python3
"""Unit tests for laubmann_dedup. Run: python test_laubmann_dedup.py (or pytest)."""

from __future__ import annotations

from laubmann_dedup import (PageRecord, cluster_pairs, generate_candidates,
                            normalize_pnum, normalize_text, quality_metrics,
                            run_detection, score_pair)


def _page(volume, pid, scan, pnum, text, rtype="ParagraphRegion", dates=None):
    starts = [{"date": d, "location": "", "date_norm": d, "offset": 0}
              for d in (dates or [])]
    return PageRecord(volume=volume, page_id=pid, scan=scan, page_number=pnum,
                      image=f"{pid}.png",
                      regions=[{"id": "r01", "type": rtype, "text": text,
                                "reading_order": 1, "entry_starts": starts}])


def test_normalize_text_umlaut_markup_hyphen():
    assert normalize_text("Gr\u00fcn<u>fink</u>") == "gruenfink"
    assert normalize_text("Beob-\nachtung") == "beobachtung"
    assert normalize_text("A   B\n\nC") == "a b c"


def test_normalize_pnum():
    assert normalize_pnum("3.") == "3"
    assert normalize_pnum("p 5/58.") == "58"
    assert normalize_pnum("XXIX") == ""


def test_pageuid_and_pid_parse():
    p = _page(6, "uuid_0021_R", 21, "25.", "text here")
    assert p.page_uid == "L06:uuid_0021_R"
    assert (p.stem, p.side, p.variant) == ("uuid", "R", "")
    full = _page(1, "uuid_0031_full", 31, "52", "x")
    assert full.variant == "full"


def test_quality_detects_repetition_loop():
    q = quality_metrics(normalize_text("der vogel singt " * 400))
    assert q["degenerate"] and "repetition_loop" in q["flags"]


def test_quality_passes_normal_prose():
    prose = ("am morgen sang die amsel im garten, spaeter zogen kiebitze "
             "ueber das feld und ein bussard kreiste hoch am himmel. ") * 6
    assert not quality_metrics(normalize_text(prose))["degenerate"]


def test_exact_duplicate_scores_high():
    t = "7. april 1917. muenchen. heute vormittag zogen viele kraniche."
    a = _page(6, "uuid_0010_R", 10, "12", t, dates=["1917-04-07"])
    b = _page(6, "uuid_0011_R", 11, "12", t, dates=["1917-04-07"])
    s = score_pair(a, b)
    assert s.confidence > 0.9 and "exact_text" in s.signals


def test_ocr_drift_still_detected():
    base = ("29. september 1928. muenchen. die raetselloesung ist da. der "
            "vermeintliche bartgeier ist ein gaensegeier, wie sich nach "
            "genauerer pruefung des praeparats im museum herausgestellt hat. ")
    a = _page(6, "uuid_0010_R", 10, "12", base * 4, dates=["1928-09-29"])
    # same page, second capture, sprinkled OCR substitutions
    drifted = (base * 4).replace("raetselloesung", "ratsellosung") \
                        .replace("gaensegeier", "gansegeier") \
                        .replace("praeparats", "preparats")
    b = _page(6, "uuid_0011_R", 11, "12", drifted, dates=["1928-09-29"])
    s = score_pair(a, b)
    assert s.confidence > 0.75
    assert "same_page_number" in s.signals and "same_entry_dates" in s.signals


def test_distinct_pages_not_flagged():
    a = _page(6, "uuid_0010_R", 10, "12",
              "heute beobachtete ich am see drei graureiher beim fischen.")
    b = _page(6, "uuid_0011_R", 11, "13",
              "gestern zogen wildgaense in grossen keilen nach sueden hin fort.")
    s = score_pair(a, b)
    assert s.confidence < 0.55


def test_containment_relation():
    body = ("22. april 1950. muenchen. silbermoeven ziehen ein, herrlich. "
            "ich fahre gegen abend per rad hinaus zum teichgebiet. ") * 4
    small = _page(22, "uuid_0060_L", 60, "84", body)
    big = _page(22, "uuid_0063", 63, "84.",
                body + "es folgen weitere lange absaetze mit vielen "
                "beobachtungen die auf der geteilten seite fehlten. " * 6)
    s = score_pair(small, big)
    assert s.relation == "containment" and "containment" in s.signals


def test_cross_volume_same_pageid():
    t = "identischer seiteninhalt aus einem zweiten pipeline-lauf hier."
    a = _page(1, "shared_0023_L", 23, "36", t)
    b = _page(15, "shared_0023_L", 23, "36", t)
    s = score_pair(a, b)
    assert "same_page_id_cross_volume" in s.signals and s.confidence > 0.9


def test_candidate_generation_layers():
    pages = [
        _page(1, "s_0010_L", 10, "5", "alpha text one two three vier fuenf"),
        _page(1, "s_0011_L", 11, "5", "alpha text one two three vier fuenf"),
        _page(1, "s_0050_L", 50, "5", "alpha text one two three vier fuenf"),
        _page(2, "s_0010_L", 10, "5", "alpha text one two three vier fuenf"),
    ]
    cands = generate_candidates(pages, scan_window=3)
    srcs = {k: v for k, v in cands.items()}
    assert any("scan_window" in v for v in srcs.values())
    assert any("page_number" in v for v in srcs.values())
    assert any("page_id_collision" in v for v in srcs.values())


def test_clustering_transitive_merge():
    t = "26. i. 48 karlsfeld. drei feldlerchen sangen ueber dem acker heute."
    pages = [_page(6, f"u_00{10+i}_R", 10 + i, "40", t, dates=["1948-01-26"])
             for i in range(3)]
    clusters, scored = run_detection(pages)
    assert len(clusters) == 1
    assert len(clusters[0].members) == 3


def test_keep_prefers_complete_over_degenerate():
    prose = ("1. januar 1928. muenchen. heute vormittag zogen viele kraniche "
             "in hohen keilen ueber die stadt nach sueden, ein herrlicher "
             "anblick bei klarem winterhimmel und leichtem frost am morgen. ")
    good = _page(6, "u_0010_R", 10, "12", prose * 4, dates=["1928-01-01"])
    # same physical page, second capture degenerated into a repetition loop
    # but still shares enough shingles/pnum/date to cluster with the good one
    bad = _page(6, "u_0011_R", 11, "12",
                prose + ("kraniche zogen ueber die stadt " * 120),
                dates=["1928-01-01"])
    assert bad.quality["degenerate"] and not good.quality["degenerate"]
    clusters, _ = run_detection([good, bad])
    assert clusters, "degenerate near-duplicate should still cluster"
    assert clusters[0].suggested_keep == good.page_uid


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {fn.__name__}: {e}")
        except Exception as e:
            print(f"ERR   {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(fns)} passed")
    return passed == len(fns)


if __name__ == "__main__":
    import sys
    sys.exit(0 if _run_all() else 1)
