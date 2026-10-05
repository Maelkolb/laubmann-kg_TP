"""Attribution check (tools/validation_ui/machine_review/attribution_check.py): candidates and the merge of two judges."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("PIL")      # the machine-review tools need Pillow (not a package dependency)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "validation_ui" / "machine_review"))
import attribution_check as ac  # noqa: E402


def test_report_signals() -> None:
    wuest = "So. 20.II.1955, 9 - 17.45 Uhr 544.Speichersee-Begehung Mit dem Postomnibus … wo ich BEZZEL und REMOLD traf"
    sig = ac.report_signals("L28-e0133a", wuest, ["Fischreiher: 2 Ob., 6 westl.Wb."], "correspondence", "field-day", "")
    assert {"boundary-correspondence", "split", "caps-names", "weekday-time-head", "ismaning-terms", "report-words"} <= set(sig)
    rathmayer = "6.Nov.55.Mit Heinz auf dem SD bis zur Insel im OB. Rabenkrähe;Saatkrähe:Abends nördlich des VKL"
    assert {"compact-date-head", "mit-heinz", "report-abbreviations"} <= set(ac.report_signals("L29-e0147", rathmayer, [], "", "field-day", ""))
    own = "7. April 1917. München. Wetter trüb. An der Isar sind noch immer sehr viele Lachmöwen zu sehen."
    assert ac.report_signals("L01-e0001", own, [own], "", "field-day", "") == []


def test_verdicts_and_names() -> None:
    answer = {"diarist": [0], "others": [{"i": [1, 2], "by": "Dr. W. Wüst", "type": "third-party-report", "c": 0.95},
                                         {"i": 3, "by": None, "c": 0.9}, {"i": [4], "by": "Laubmann", "c": 0.9}]}
    v = ac.verdicts(answer, [0, 1, 2, 3, 4, 9])
    assert v[0] == ("diarist",) and v[4] == ("diarist",)
    assert v[1][:3] == ("other", "Dr. W. Wüst", "third-party-report") and v[3][:3] == ("other", None, "third-party-report")
    assert 9 not in v
    assert ac.surname("Dr. W. Wüst") == ac.surname("Walter Wuest") == "wuest"
    diary = "Walter Wüst … Walter Wüst … W. Wüst … Einhard Bezzel … Einhard Bezzel … Herbert Bezzel … nach Erdt"
    assert ac.pick_name("W. Wüst", "Walter Wüst", diary) == "Walter Wüst"
    assert ac.pick_name("Herbert Bezzel", "Einhard Bezzel", diary) == "Einhard Bezzel"
    assert ac.pick_name("Christian Daniel Erdt", "Chr. Erdt", diary) == "Chr. Erdt"


def test_merge_applies_only_what_both_judges_say(tmp_path: Path) -> None:
    root = tmp_path
    (root / "gemini").mkdir()
    (root / "claude" / "answers").mkdir(parents=True)
    (root / "claude" / "dossiers").mkdir(parents=True)
    with open(root / "candidates.csv", "w", newline="", encoding="utf-8") as h:
        csv.writer(h).writerows([["entry_id", "entry_uid", "n_records", "n_diarist", "signals", "pages"], ["L1-e1", "e_1", 5, 5, "split", ""]])
    recs = [{"i": 0, "name": "Star"}, {"i": 1, "name": "Kiebitz", "with": ["Walter Wüst", "Heinz Remold"]}, {"i": 2, "name": "Elster"},
            {"i": 3, "name": "Dohle"}, {"i": 4, "name": "Amsel"}]
    block = "### Records credited to Laubmann\n" + "\n".join(json.dumps(r, ensure_ascii=False) for r in recs)
    (root / "claude" / "dossiers" / "L1-e1.json").write_text(json.dumps({"entry_id": "L1-e1", "pages": [], "block": block}), encoding="utf-8")
    gem = {"report": "part", "diarist": [0], "others": [{"i": [1, 2], "by": "W. Wüst", "type": "third-party-report", "c": 0.95},
                                                       {"i": [3], "by": None, "c": 0.9}, {"i": [4], "by": "Einhard Bezzel", "c": 0.95}]}
    cla = {"report": "part", "diarist": [0, 4], "others": [{"i": [1], "by": "Walter Wüst", "type": "third-party-report", "c": 0.9},
                                                          {"i": [2, 3], "by": "Werner Rathmayer", "c": 0.95}]}
    (root / "gemini" / "L1-e1.json").write_text(json.dumps({"entry_id": "L1-e1", "entry_uid": "e_1", "records": [0, 1, 2, 3, 4], "answer": gem}))
    (root / "claude" / "answers" / "L1-e1.json").write_text(json.dumps(cla))

    class A:
        out, csv, date, corpus = str(root), None, "2026-10-05", None
    ac.cmd_merge(A)
    rows = list(csv.DictReader(open(root / "attribution_machine.csv", encoding="utf-8")))
    got = {(r["obs_index"], r["field"]): r["new_value"] for r in rows}
    assert got[("1", "observer")] == "W. Wüst" and got[("1", "record_type")] == "third-party-report"   # no corpus: fewer words
    assert got[("1", "co_observers")] == "Heinz Remold"                  # the author was listed as Laubmann's companion
    assert ("2", "observer") not in got and got[("2", "record_type")] == "third-party-report"   # Wüst vs Rathmayer: author unknown
    assert got[("3", "record_type")] == "third-party-report" and ("3", "observer") not in got   # not Laubmann, author unknown
    assert not any(k[0] in ("0", "4") for k in got)                        # diarist (both), and diarist vs Bezzel
    assert {r["confidence"] for r in rows if r["obs_index"] == "1"} == {"0.995"} and {r["agreement"] for r in rows} == {"2"}


def test_text_authors_from_cover_notes_signatures_and_series() -> None:
    assert ac.text_authors("… Werner Rathmayer, Freising, schickt mir die nachfolgenden Beobachtungsberichte:", "6.Nov.55.Mit Heinz") == {"rathmayer"}
    assert ac.text_authors("", "Auf der nächsten Seite folgt ein Bericht aus Ismaning von Einhard Bezzel vom 19. III.") == {"bezzel"}
    assert ac.text_authors("", "Mo. 26.IX.1955 565.Speichersee-Begehung Haubentaucher: 5 Ex.") == {"wuest"}
    assert ac.text_authors("", "… 1 W.im Ob. bei Neufinsing. gez.Heinz Remold.") == {"remold"}
    assert ac.text_authors("", "7. April 1917. München. Wetter trüb. Lachmöwen an der Isar.") == set()


def test_entry_spelling_reuses_the_person_of_the_entry() -> None:
    assert ac.entry_spelling("Chr. Erdt", ["Chr. D. Erdt", "Hans Müller"]) == "Chr. D. Erdt"
    assert ac.entry_spelling("Walter Wüst", ["Heinrich Wüst"]) == "Walter Wüst"            # conflicting first name
    assert ac.entry_spelling("Walter Wüst", ["Heinrich Wüst", "W. Wüst"]) == "W. Wüst"
    assert ac.entry_spelling("Einhard Bezzel", ["Einhart Bezzel"]) == "Einhard Bezzel"
    assert ac.entry_spelling("Werner Rathmayer", []) == "Werner Rathmayer"
    assert ac.entry_spelling("Wüst", ["Heinrich Wüst"]) == "Wüst"
    assert ac.pick_name("Walter Wüst", "Wüst", "Wüst … Wüst … Walter Wüst") == "Walter Wüst"
