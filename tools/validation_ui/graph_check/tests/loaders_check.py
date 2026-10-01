"""Feed an exported review folder through the pipeline's own loaders (run with the repo's Python).

    python tests/loaders_check.py <folder with observation_corrections.csv, value_corrections.csv, ...> [entries.json]

Prints one JSON line: the rows every loader returns and the loaders' warnings. With ``entries.json``
([{uid, id, date, place, observations: [[written, index], ...]}, ...] — the records of the entries the
test decided on) the value and observation corrections are also APPLIED to model entries built from it,
in the pipeline's order, and the result is reported (records per entry, flags)."""
import dataclasses
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
from laubmann_kg.extraction.reading import load_transcript_decisions                      # noqa: E402
from laubmann_kg.kg.model import DiaryEntry, Observation, Place, Taxon                    # noqa: E402
from laubmann_kg.normalization.corrections import apply_corrections, load_corrections      # noqa: E402
from laubmann_kg.normalization.observation_corrections import (                           # noqa: E402
    FIELDS, apply_observation_corrections, load_observation_corrections)
from laubmann_kg.normalization import corrections as corrections_mod                       # noqa: E402
from laubmann_kg.qa import load_qa_decisions                                              # noqa: E402
from laubmann_kg.review.identities import IDENTITY_FIELDS, Identities                     # noqa: E402
from laubmann_kg.review.readings import READING_FIELDS, load_readings                     # noqa: E402

warnings = []


class Catch(logging.Handler):
    def emit(self, record):
        if record.levelno >= logging.WARNING:
            warnings.append(record.getMessage())


logging.getLogger().addHandler(Catch())
logging.getLogger().setLevel(logging.INFO)
d = Path(sys.argv[1])
oc = load_observation_corrections(d / "observation_corrections.csv")
vc = load_corrections(d / "value_corrections.csv")
td = load_transcript_decisions(d / "transcript_decisions.csv")
tc = load_readings(d / "text_corrections.csv")
qd = load_qa_decisions(d / "qa_decisions.csv")
ids = Identities.load(d / "identities.csv")
out = {
    "contract": {"observation_corrections": FIELDS, "value_corrections": corrections_mod.FIELDS, "text_corrections": READING_FIELDS, "identities": IDENTITY_FIELDS},
    "observation_corrections": [dict(dataclasses.asdict(c), add=dict(c.add)) for c in oc],
    "value_corrections": [dataclasses.asdict(c) for c in vc],
    "transcript_decisions": [{"entry_uid": k[0], "old_text": k[1], "new_text": k[2], "decision": v[0], "final_text": v[1]} for k, v in td.items()],
    "text_corrections": [dataclasses.asdict(r) for r in tc],
    "qa_decisions": [{"entry_uid": k[0], "reason": k[1], "value": k[2], "decision": v} for k, v in qd.items()],
    "identities": [dict(dataclasses.asdict(i), table=t) for t, table in (("forms", ids.forms), ("links", ids.links)) for sec in table.values() for i in sec.values()],
}

if len(sys.argv) > 2:      # apply to model entries, as the pipeline does: value corrections, then observation corrections
    spec = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    entries = []
    for e in spec:
        entry = DiaryEntry(entry_uid=e["uid"], entry_id=e["id"], volume=1, page_uid="p", page_id="p", region_uid=None, scan=None,
                           entry_date=e.get("date") or None, verbatim_event_date=None, location_raw=e.get("place") or "", text_clean="t")
        entry.place = Place(verbatim=e["place"], canonical=e["place"], kind="settlement") if e.get("place") else None
        entry.observations = [Observation(entry_uid=e["uid"], taxon=Taxon(w, is_bird=True), verbatim_notes=f"n{i}", index=i, place=entry.place)
                              for w, i in e["observations"]]
        entries.append(entry)
    n1, f1 = apply_corrections(entries, vc)
    n2, f2 = apply_observation_corrections(entries, oc)
    out["applied"] = {
        "value_changes": n1, "observation_rows": n2,
        "flags": [[f.entry_uid, f.reason, f.value] for f in f1 + f2],
        "entries": {e.entry_uid: {"date": e.entry_date, "kind": e.entry_kind, "place": e.place.name if e.place else None,
                                  "observations": [{"index": o.index, "name": o.taxon.vernacular_de, "sci": o.taxon.scientific_name, "gbif": o.taxon.gbif_key,
                                                    "count": o.individual_count, "min": o.count_min, "max": o.count_max, "qualifier": o.count_qualifier,
                                                    "locality": o.locality.name if o.locality else None, "date": o.event_date,
                                                    "observer": o.observer.name if o.observer else None, "co": [p.name for p in o.co_observers],
                                                    "record_type": o.record_type, "sex": o.sex, "status": o.occurrence_status, "text": o.verbatim_notes,
                                                    "remarks": o.occurrence_remarks} for o in e.observations]} for e in entries},
    }
out["warnings"] = warnings
sys.stdout.reconfigure(encoding="utf-8")      # Windows consoles default to cp1252
print(json.dumps(out, ensure_ascii=False))
