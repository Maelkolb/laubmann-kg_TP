"""Machine review of the extraction: dossiers of sample entries.

For a stratified random sample of diary entries (by volume, entries with at
least one observation) one folder each with the scan pages the entry spans
(JPEG), the transcription, and everything the graph says about the entry:
date, place, kind, observations (written name, linked taxon, count, locality,
evidence, behaviour, sex, breeding, record type, observer), persons with
roles, travel legs, weather, habitats. An agent reads scan and transcription
and checks every record: right, wrong (which field), spurious, and lists what
the text states that the graph misses. Findings are keyed by entry uid and
observation index, so they can be re-applied after a re-extraction.

    python tools/validation_ui/machine_review/prepare_entries.py payload.b64 triples.pkl --out <workdir> \
        --pages "<HistOrniGraph_output>" [--n 60] [--seed 20260930]
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import pickle
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PageImages, instructions, load_payload, page_jpeg, write_json  # noqa: E402

INSTRUCTIONS = """# Extraction check — instructions

You are checking what a knowledge graph extracted from one entry of the ornithological field diaries of Alfred Laubmann (Bavaria, 1917–1965; handwritten German, Latin cursive with Kurrent elements; the transcription is machine-made and can misread words). Work carefully but do not over-deliberate. Read the dossier, look at every page image ONCE with the Read tool (the entry may run over a page break; the pages are in order), then write the answer file; no other tools are needed.

Files (N = the dossier number you were given, three digits):
- Dossier: `{root}/entries/dossier_N/dossier.json` — `entry` (id, date as the graph has it, verbatim date, entry place, kind), `transcription` (the machine transcription of the entry), `pages` (image files, in reading order, with the printed page numbers), and `graph`: `observations` (index, written name, linked taxon with scientific name, count and qualifier, locality as written, evidence kinds, behaviour, sex, life stage, breeding evidence, record type, observer, event date when it differs from the entry date), `persons` (name, roles), `travel` (legs with from/to/via/mode), `weather`, `habitats`.
- Answer: `{root}/entries/answers/dossier_N.json`

Check, against the scan first and the transcription second:
1. Every observation: is there such a record in the text? Is the species right (misread names are common — decide from the handwriting), the count (a number, "einige", "viele", a pair, "zahlreich"), the locality, the date (records of earlier days quoted in an entry carry their own date), the breeding/behaviour statements, the observer (third-party reports "nach X", "teste Y")? Give `verdict` `ok` (all fields right or only trivial issues), `wrong` (list the wrong fields in `fields` and the right values in `correction`), `spurious` (the text has no such record: e.g. a place or a person name extracted as a bird, a negated or hypothetical statement — say why), `unsure`.
2. Missing records: species (or counts of a species) the text clearly reports that have no observation in the graph; persons, travel legs, weather statements missing. List them in `missing` with the text passage.
3. Entry-level fields: date, place, kind — right or not, with the correction.
4. Transcription: name the misread words that matter (species, places, persons, numbers) with the correct reading; ignore harmless typos.

Judge the scan as the ground truth when it is legible; when it is not, say so and judge by the transcription with lower confidence. A record's count is right when it matches the text's quantity in kind (an exact number = exact; "einige" = plural unspecified, etc.); a missing count is only wrong when the text states one.

Write the answer as JSON:
`{"dossier": N, "entry_id": "...", "entry_uid": "...", "entry_fields": {"date_ok": true|false|null, "date_correction": "YYYY-MM-DD or null", "place_ok": true|false|null, "place_correction": "text or null", "kind_ok": true|false|null, "note": "short, German"}, "observations": [{"index": <graph index>, "written": "...", "verdict": "ok|wrong|spurious|unsure", "fields": ["species","count","locality","date","breeding","behaviour","observer","other"], "correction": {"species_de": "...", "sci": "...", "count": "...", "locality": "...", "date": "...", "other": "..."} or null, "confidence": 0.0-1.0, "reason": "one short sentence, German"}], "missing": [{"kind": "observation|person|travel|weather|other", "text": "the passage", "species_de": "German name or null", "sci": "scientific name or null", "count": "as written or null", "note": "short, German"}], "misreadings": [{"transcribed": "...", "correct": "...", "matters_for": "species|place|person|count|date|other"}], "scan_legible": true|false, "summary": "two or three sentences in German: what is right, what is wrong"}`

Then reply with only the answer file path and one line `entry: n observations, k ok / wrong / spurious, m missing`.
"""


def loc(u) -> str:
    u = str(u)
    return u.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("payload")
    ap.add_argument("triples")
    ap.add_argument("--out", required=True)
    ap.add_argument("--pages", required=True)
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--seed", type=int, default=20260930)
    ap.add_argument("--max-pages", type=int, default=3)
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

    entries = {}
    for s, ts in typ.items():
        if "DiaryEntry" in ts:
            entries[one(s, "identifier")] = s
    # sample: entries with observations, at most max_pages pages, stratified by volume
    obs_n = collections.Counter(m[1] for m in T["men"])
    by_vol = collections.defaultdict(list)
    for ei, n in obs_n.items():
        e = E[ei]
        if n >= 2 and 1 <= len(e[8]) <= args.max_pages and e[0] in entries:
            by_vol[e[5]].append(ei)
    rng = random.Random(args.seed)
    total = sum(len(v) for v in by_vol.values())
    sample = []
    for vol, idx in sorted(by_vol.items()):
        k = max(1, round(args.n * len(idx) / total))
        sample += rng.sample(idx, min(k, len(idx)))
    rng.shuffle(sample)
    sample = sample[: args.n]
    print(f"sample {len(sample)} entries from {total} candidates")

    def obs_index(s, entry_uid, written):
        want = loc(s).replace("obs_", "")
        for i in range(1000):
            if hashlib.sha1(f"{entry_uid}|{written}|{i}".encode("utf-8")).hexdigest()[:12] == want:
                return i
        return 10 ** 6

    edir = root / "entries"
    (edir / "answers").mkdir(parents=True, exist_ok=True)
    for k, ei in enumerate(sample, 1):
        e = E[ei]
        s = entries[e[0]]
        d = edir / f"dossier_{k:03d}"
        d.mkdir(exist_ok=True)
        imgs = []
        for pidx in e[8]:
            pg = PG[pidx]
            png = pages.path(pg[0])
            if not png:
                continue
            name = f"page_{len(imgs) + 1}.jpg"
            (d / name).write_bytes(page_jpeg(png, 1400))
            imgs.append({"file": str((d / name)).replace("\\", "/"), "scan": pg[2], "side": pg[3], "printed_page": pg[4]})
        observations = []
        for o in out[s].get("containsObservation", []):
            tx = out[o].get("observedTaxon", [None])[0]
            written = one(o, "verbatimIdentification") or (label(tx) if tx is not None else "")
            rec = {"index": obs_index(o, e[1], written), "written": written,
                   "taxon": label(tx) if tx is not None else None, "sci": one(tx, "scientificName") or None,
                   "count": one(o, "individualCount") or None, "count_qualifier": one(o, "countQualifier") or None,
                   "count_min": one(o, "countMin") or None, "count_max": one(o, "countMax") or None,
                   "status": one(o, "occurrenceStatus") or None, "locality": one(o, "verbatimLocality") or None,
                   "evidence": [loc(x) for x in out[o].get("evidenceKind", [])] or None,
                   "vocalisations": [one(v, "callTranscription") or one(v, "callType") for v in out[o].get("hasVocalisation", [])] or None,
                   "behaviour": many(o, "behavior") or None, "sex": one(o, "sex") or None, "life_stage": one(o, "lifeStage") or None,
                   "breeding": one(o, "reproductiveCondition") or one(o, "breedingEvidence") or None,
                   "record_type": one(o, "recordType") or None,
                   "observer": (label(out[o]["recordedBy"][0]) if out[o].get("recordedBy") and loc(out[o]["recordedBy"][0]) != "person_c6b2ff6250e5" else None),
                   "event_date": one(o, "eventDate") if one(o, "eventDate") != e[2] else None,
                   "notes": (one(o, "verbatimNotes") or None)}
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
                travel.append({"from": label(out[leg]["departurePlace"][0]) if out[leg].get("departurePlace") else None,
                               "to": label(out[leg]["arrivalPlace"][0]) if out[leg].get("arrivalPlace") else None,
                               "via": [label(x) for x in out[leg].get("viaPlace", [])] or None,
                               "mode": one(leg, "transportMode") or None, "note": one(leg, "note") or None})
        weather = [{"verbatim": one(w, "weatherVerbatim"), "temperature": one(w, "temperatureValue") or None,
                    "unit": one(w, "temperatureUnit") or None, "precipitation": one(w, "precipitation") or None,
                    "sky": one(w, "skyCondition") or None} for w in out[s].get("hasWeather", [])]
        habitats = sorted({label(h) for o in out[s].get("containsObservation", []) for h in out[o].get("habitat", []) if str(h).startswith("http")})
        dossier = {"dossier": k, "entry": {"id": e[0], "uid": e[1], "date": e[2], "date_verbatim": e[3], "kind": e[4],
                                            "volume": e[5], "place": e[6], "place_verbatim": e[9]},
                   "pages": imgs, "transcription": e[7],
                   "graph": {"observations": observations, "persons": persons, "travel": travel, "weather": weather, "habitats": habitats}}
        write_json(d / "dossier.json", dossier)
    instructions(edir / "INSTRUCTIONS.md", INSTRUCTIONS, root=str(root).replace("\\", "/"))
    print(f"{len(sample)} dossiers in {edir}")


if __name__ == "__main__":
    main()
