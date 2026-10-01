"""Reviewer decisions on QA flags (review/qa_decisions.csv of the validation UI)."""

from laubmann_kg.kg.model import DiaryEntry, Observation, Taxon
from laubmann_kg.qa import run_qa

HEAD = "entry_uid,entry_id,reason,value,decision,note,reviewed_by,reviewed_at"


def _entry(uid, taxon):
    e = DiaryEntry(uid, "L08-" + uid, 8, "p", "page_A", "r", None, "1930-08-16", "16. August 1930", "Pöcking", "text")
    e.observations = [Observation(uid, taxon, "Notiz", index=0)]
    return e


def test_false_alarm_keeps_the_record_and_drops_the_flag(tmp_path):
    path = tmp_path / "qa_decisions.csv"
    path.write_text("\n".join([HEAD, "e1,L08-e1,non_bird,Ringeltaube,false_alarm,ist ein Vogel,A,2026-10-01"]) + "\n",
                    encoding="utf-8")
    dove = Taxon("Ringeltaube", is_bird=False)
    fox = Taxon("Fuchs", is_bird=False)
    kept, flags = run_qa([_entry("e1", dove), _entry("e2", fox)], {"decisions": str(path), "misdate": False})
    by_uid = {e.entry_uid: e for e in kept}
    assert len(by_uid["e1"].observations) == 1          # the reviewer said: a bird
    assert not by_uid["e2"].observations               # still excluded
    assert [(f.entry_uid, f.reason) for f in flags if f.reason == "non_bird"] == [("e2", "non_bird")]
