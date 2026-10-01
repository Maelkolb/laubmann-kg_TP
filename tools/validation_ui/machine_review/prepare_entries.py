"""Machine review of the extraction: dossiers of sample entries.

For a stratified random sample of diary entries one folder each with the scan
pages the entry spans (JPEG), the transcription the extraction read (after the
visual reading), every correction the visual reading made or proposed, and
everything the graph and the Darwin Core Archive say about the entry: date,
place, kind, observations (written name, linked taxon, count, locality,
evidence, vocalisation, behaviour, sex, breeding, record type, observers,
georeference of the DwC-A occurrence), persons with roles, travel legs,
weather, habitats. An agent reads scan and transcription and checks every
record (right, wrong: which field, spurious), lists what the text states that
the graph misses, and judges every transcript correction (right, partly,
wrong). Findings are keyed by entry uid and observation index, so they can be
re-applied after a re-extraction.

Strata (``--strata``, default for the final graph): ``random`` entries with
≥ 2 observations proportional to the volumes, ``poor`` entries whose
transcript the reading judged poor, ``report`` entries with third-party
records (reports, letters, literature), ``long`` entries with ≥ 30
observations, ``empty`` entries with text but no observation (recall).

    python tools/validation_ui/machine_review/prepare_entries.py payload.b64 triples.pkl --out <workdir> \\
        --pages data/pages_jpg --review <export>/review --dwca <export>/dwca \\
        [--strata random:60,poor:20,report:15,long:10,empty:10] [--seed 20261001]
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import pickle
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PageImages, instructions, load_payload, page_jpeg, write_json  # noqa: E402

INSTRUCTIONS = """# Extraction check — instructions

You are checking what a knowledge graph extracted from one entry of the ornithological field diaries of Alfred Laubmann (Bavaria and his travels, 1917–1965; handwritten German, Latin cursive with Kurrent elements, and typed inserts). The transcription is machine-made; before extraction a vision model compared it with the scan and corrected it (the list of its corrections is in the dossier). Work carefully but do not over-deliberate. Read the dossier, look at every page image ONCE with the Read tool (the pages are in reading order; they may also show the end of the previous and the start of the next entry — only this entry counts), then write the answer file; no other tools are needed. Write nothing else anywhere.

Files (N = the dossier number you were given, three digits):
- Dossier: `{root}/entries/dossier_N/dossier.json` — `entry` (id, uid, date as the graph has it, verbatim date, entry place, kind, stratum), `transcription` (the text the extraction read, i.e. AFTER the corrections), `transcript_corrections` (i, old = transcription as delivered, new = the vision model's reading, applied = whether it was applied to the text), `pages` (image files with printed page numbers), and `graph`: `observations` (index, written name, taxon with scientific name, counts, locality, the DwC-A georeference `georef` = [locality, lat, lon, uncertainty m], evidence, vocalisation, behaviour, sex, life stage, breeding, record type, observers, own event date when it differs from the entry's), `persons` (name, roles), `travel`, `weather`, `habitats`.
- Answer: `{root}/entries/answers/dossier_N.json`

Check, against the scan first and the transcription second:
1. Every observation: is there such a record in this entry's text? Species right (decide from the handwriting; misread names are common), count (exact number / range / "einige", "viele", a pair; partial counts of one record are summed), locality, date (a record of another day quoted in the entry carries its own date), breeding/behaviour/vocalisation statements, observers and record type (third-party reports "nach X", "teste Y", letters; "ich" in a pasted report is its author). `verdict`: `ok` (all fields right or only trivial issues), `wrong` (wrong fields in `fields`, right values in `correction`), `spurious` (no such record: a place or person read as a bird, a negated/hypothetical/comparative statement, a list number read as a count — say why), `unsure`. Georeference: `georef` wrong only when the point is clearly not the named place (another village of the same name far away, a country centroid for a precise site) → field `georef`.
2. Missing records: species (or counts) the text clearly reports that have no observation; persons, travel legs, weather statements missing. List them in `missing` with the passage.
3. Entry-level fields: date, place, kind — right or not, with the correction.
4. Transcript corrections: judge EVERY item of `transcript_corrections` against the scan: `right` (new is what the page shows), `partly` (closer than old but not exact, or right word but also changed something else), `wrong` (old was right, or new is another misreading, or new inserts text of another entry), `unclear` (illegible). Give the exact page text in `better` when it is neither old nor new. Also list further misreadings that matter (species, places, persons, numbers, dates) in `misreadings`.

The scan is the ground truth when legible; when it is not, say so and judge by the transcription with lower confidence. A missing count is only wrong when the text states one.

Answer JSON (German for free text):
`{"dossier": N, "entry_id": "...", "entry_uid": "...", "entry_fields": {"date_ok": true|false|null, "date_correction": "YYYY-MM-DD or null", "place_ok": true|false|null, "place_correction": "text or null", "kind_ok": true|false|null, "note": "short"}, "observations": [{"index": <graph index>, "written": "...", "verdict": "ok|wrong|spurious|unsure", "fields": ["species","count","locality","georef","date","breeding","behaviour","vocalisation","observer","record_type","other"], "correction": {"species_de": "...", "sci": "...", "count": "...", "locality": "...", "date": "...", "observer": "...", "other": "..."} or null, "confidence": 0.0-1.0, "reason": "one short sentence"}], "missing": [{"kind": "observation|person|travel|weather|other", "text": "the passage", "species_de": "German name or null", "sci": "scientific name or null", "count": "as written or null", "note": "short"}], "transcript_checks": [{"i": <i>, "verdict": "right|partly|wrong|unclear", "better": "exact page text or null"}], "misreadings": [{"transcribed": "...", "correct": "...", "matters_for": "species|place|person|count|date|other"}], "scan_legible": true|false, "summary": "two or three sentences: what is right, what is wrong"}`

Then reply with only the answer file path and one line `entry: n observations, k ok / wrong / spurious, m missing; corrections r right / p partly / w wrong`.
"""

DIARIST = "person_c6b2ff6250e5"


def loc(u) -> str:
    u = str(u)
    return u.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def read_csv(path, delimiter=","):
    p = Path(path) if path else None
    if not p or not p.exists():
        return []
    with open(p, encoding="utf-8", newline="") as h:
        return list(csv.DictReader(h, delimiter=delimiter))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("payload")
    ap.add_argument("triples")
    ap.add_argument("--out", required=True)
    ap.add_argument("--pages", required=True, help="HistOrniGraph_output (PNG) or a folder of <page_id>.jpg")
    ap.add_argument("--review", default=None, help="the export's review/ (transcript_corrections.csv, qa_flags.csv)")
    ap.add_argument("--dwca", default=None, help="the export's dwca/ (occurrence.txt)")
    ap.add_argument("--strata", default="random:60,poor:20,report:15,long:10,empty:10")
    ap.add_argument("--n", type=int, default=None, help="old interface: only the random stratum with n entries")
    ap.add_argument("--seed", type=int, default=20261001)
    ap.add_argument("--max-pages", type=int, default=3)
    ap.add_argument("--exclude", default=None, help="file with entry uids already checked (one per line)")
    args = ap.parse_args()
    P = load_payload(args.payload)
    root = Path(args.out).resolve()
    E, PG = P["E"], P["PG"]
    T = P["taxon"]
    pages = PageImages(Path(args.pages))

    print("loading triples …")
    out = collections.defaultdict(lambda: collections.defaultdict(list))
    typ = {}
    for s, p, o in pickle.load(open(args.triples, "rb")):
        pn = loc(p)
        if pn == "type":
            typ.setdefault(s, set()).add(loc(o))
        else:
            out[s][pn].append(o)

    def one(s, p, d=""):
        v = out[s].get(p) if s is not None else None
        return str(v[0]) if v else d

    def many(s, p):
        return [str(x) for x in out[s].get(p, [])]

    def label(s):
        return one(s, "prefLabel") or one(s, "label") or one(s, "name") or loc(s)

    entries = {one(s, "identifier"): s for s, ts in typ.items() if "DiaryEntry" in ts}
    corr = collections.defaultdict(list)
    for r in read_csv(Path(args.review) / "transcript_corrections.csv" if args.review else None):
        corr[r["entry_uid"]].append(r)
    qa = collections.defaultdict(set)
    for r in read_csv(Path(args.review) / "qa_flags.csv" if args.review else None):
        qa[r.get("entry_uid", "")].add(r.get("reason", ""))
    occ_rows = {r["occurrenceID"]: r for r in read_csv(Path(args.dwca) / "occurrence.txt" if args.dwca else None, "\t")}
    excluded = set(Path(args.exclude).read_text(encoding="utf-8").split()) if args.exclude else set()

    # ------------------------------------------------------------ strata
    obs_n = collections.Counter(m[1] for m in T["men"])
    third = set()
    for s, ts in typ.items():
        if "Observation" in ts and one(s, "recordType") in ("third-party-report", "correspondence", "literature-record"):
            e = out[s].get("isPartOf", [None])[0]
            if e is not None:
                third.add(one(e, "identifier"))

    def eligible(ei, max_pages):
        e = E[ei]
        return e[0] in entries and e[1] not in excluded and 1 <= len(e[8]) <= max_pages

    pools = {
        "random": [ei for ei in range(len(E)) if obs_n[ei] >= 2 and eligible(ei, args.max_pages)],
        "poor": [ei for ei in range(len(E)) if obs_n[ei] >= 1 and "transcript_poor" in qa.get(E[ei][1], ()) and eligible(ei, args.max_pages)],
        "report": [ei for ei in range(len(E)) if obs_n[ei] >= 1 and E[ei][0] in third and eligible(ei, args.max_pages)],
        "long": [ei for ei in range(len(E)) if obs_n[ei] >= 30 and eligible(ei, args.max_pages + 1)],
        "empty": [ei for ei in range(len(E)) if obs_n[ei] == 0 and len(E[ei][7] or "") >= 300 and eligible(ei, 2)],
    }
    want = [("random", args.n)] if args.n else [(k, int(v)) for k, v in (x.split(":") for x in args.strata.split(","))]
    rng = random.Random(args.seed)
    sample, taken = [], set()
    for name, k in want:
        pool = [ei for ei in pools[name] if ei not in taken]
        if name == "random":           # proportional to the volumes
            by_vol = collections.defaultdict(list)
            for ei in pool:
                by_vol[E[ei][5]].append(ei)
            pick = []
            for vol, idx in sorted(by_vol.items()):
                pick += rng.sample(idx, min(len(idx), max(1, round(k * len(idx) / max(1, len(pool))))))
            rng.shuffle(pick)
            pick = pick[:k]
        else:
            pick = rng.sample(pool, min(k, len(pool)))
        taken.update(pick)
        sample += [(ei, name) for ei in pick]
        print(f"stratum {name}: {len(pick)} of {len(pools[name])} candidates")
    rng.shuffle(sample)

    def obs_index(s, entry_uid, written):
        want_ = loc(s).replace("obs_", "")
        for i in range(1000):
            if hashlib.sha1(f"{entry_uid}|{written}|{i}".encode("utf-8")).hexdigest()[:12] == want_:
                return i
        return 10 ** 6

    edir = root / "entries"
    (edir / "answers").mkdir(parents=True, exist_ok=True)
    manifest = []
    for k, (ei, stratum) in enumerate(sample, 1):
        e = E[ei]
        s = entries[e[0]]
        d = edir / f"dossier_{k:03d}"
        d.mkdir(exist_ok=True)
        imgs = []
        for pidx in e[8]:
            pg = PG[pidx]
            src = pages.path(pg[0])
            if not src:
                continue
            name = f"page_{len(imgs) + 1}.jpg"
            (d / name).write_bytes(page_jpeg(src, 1400))
            imgs.append({"file": str((d / name)).replace("\\", "/"), "scan": pg[2], "side": pg[3], "printed_page": pg[4]})
        observations = []
        for o in out[s].get("containsObservation", []):
            tx = out[o].get("observedTaxon", [None])[0]
            written = one(o, "verbatimIdentification") or (label(tx) if tx is not None else "")
            place = out[o].get("observedAt", [None])[0]
            dw = occ_rows.get(str(o), {})
            observers = [label(p) for p in out[o].get("recordedBy", [])]
            rec = {"index": obs_index(o, e[1], written), "written": written,
                   "taxon": label(tx) if tx is not None else None, "sci": one(tx, "scientificName") or None,
                   "rank": one(tx, "taxonRank") or None, "is_bird": one(tx, "isBird") or None,
                   "count": one(o, "individualCount") or None, "count_min": one(o, "individualCountMin") or None,
                   "count_max": one(o, "individualCountMax") or None, "count_qualifier": one(o, "countQualifier") or None,
                   "status": one(o, "occurrenceStatus") or None, "locality": one(o, "verbatimLocality") or None,
                   "place": label(place) if place is not None else None,
                   "georef": [dw.get("locality"), dw.get("decimalLatitude"), dw.get("decimalLongitude"),
                              dw.get("coordinateUncertaintyInMeters")] if dw.get("decimalLatitude") else None,
                   "evidence": many(o, "evidenceKind") or None, "call_type": many(o, "callType") or None,
                   "call_transcription": many(o, "callTranscription") or None,
                   "behaviour": many(o, "behavior") or None, "movement": one(o, "movementKind") or None,
                   "flight_direction": one(o, "flightDirection") or None, "time_of_day": one(o, "timeOfDay") or None,
                   "sex": one(o, "sex") or None, "life_stage": one(o, "lifeStage") or None, "vitality": one(o, "vitality") or None,
                   "breeding": one(o, "breedingEvidence") or None, "record_type": one(o, "recordType") or None,
                   "observers": observers if observers != ["Alfred Laubmann"] else None,
                   "identification_qualifier": one(o, "identificationQualifier") or None,
                   "habitat": [label(h) for h in out[o].get("habitat", []) if str(h).startswith("http")] or None,
                   "microhabitat": many(o, "microhabitat") or None,
                   "event_date": one(o, "eventDate") if one(o, "eventDate") != e[2] else None,
                   "notes": one(o, "verbatimNotes") or None}
            observations.append({k2: v for k2, v in rec.items() if v not in (None, [], "")})
        observations.sort(key=lambda r: r["index"])
        roles = collections.defaultdict(set)
        for pred, role in {"mentionsCompanion": "Begleiter", "mentionsSource": "Quelle", "mentionsCollector": "Sammler",
                           "mentionsCitedAuthor": "zitiert", "mentionsOther": "sonstige"}.items():
            for p in out[s].get(pred, []):
                roles[p].add(role)
        persons = [{"name": label(p), "roles": sorted(roles.get(p, {"erwähnt"}))} for p in out[s].get("mentionsPerson", [])]
        travel = []
        for tv in out[s].get("containsTravelEvent", []):
            for leg in out[tv].get("hasLeg", []):
                travel.append({k2: v for k2, v in {
                    "from": label(out[leg]["departurePlace"][0]) if out[leg].get("departurePlace") else None,
                    "to": label(out[leg]["arrivalPlace"][0]) if out[leg].get("arrivalPlace") else None,
                    "via": [label(x) for x in out[leg].get("viaPlace", [])] or None,
                    "mode": one(leg, "transportMode") or None, "note": one(leg, "note") or None}.items() if v})
        weather = [{k2: v for k2, v in {"verbatim": one(w, "weatherVerbatim"), "temperature": one(w, "temperatureValue"),
                                        "unit": one(w, "temperatureUnit"), "precipitation": one(w, "precipitation"),
                                        "sky": one(w, "skyCondition")}.items() if v} for w in out[s].get("hasWeather", [])]
        tc = [{"i": i, "old": r["old_text"], "new": r["new_text"], "applied": r.get("applied") == "y"}
              for i, r in enumerate(corr.get(e[1], []))]
        dossier = {"dossier": k, "entry": {"id": e[0], "uid": e[1], "date": e[2], "date_verbatim": e[3], "kind": e[4],
                                            "volume": e[5], "place": e[6], "place_verbatim": e[9], "stratum": stratum,
                                            "qa_flags": sorted(qa.get(e[1], ())) or None},
                   "pages": imgs, "transcription": e[7], "transcript_corrections": tc,
                   "graph": {"observations": observations, "persons": persons, "travel": travel, "weather": weather}}
        write_json(d / "dossier.json", dossier)
        manifest.append({"dossier": k, "entry_id": e[0], "entry_uid": e[1], "stratum": stratum, "pages": len(imgs),
                         "observations": len(observations), "corrections": len(tc)})
    write_json(edir / "manifest.json", manifest)
    instructions(edir / "INSTRUCTIONS.md", INSTRUCTIONS, root=str(root).replace("\\", "/"))
    print(f"{len(sample)} dossiers in {edir}; observations {sum(m['observations'] for m in manifest)}, "
          f"corrections {sum(m['corrections'] for m in manifest)}, pages {sum(m['pages'] for m in manifest)}")


if __name__ == "__main__":
    main()
