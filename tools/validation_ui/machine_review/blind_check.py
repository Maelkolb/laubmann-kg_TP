"""Blind second check of every record: a vision model reads each record anew without seeing the graph's values.

The record check (record_check.py) shows the model the graph's values and asks whether they are right; the
audit of 3 October found that it accepts most wrong places, observers and dates. This check gives the model the
page scans, the transcription and, for every record, only its index, the bird name as written and the passage
it was taken from. The model states species, count, status, place, date, observers and record type itself.
Places and persons are chosen from numbered lists of everything the graph holds for the entry (which record has
which is not shown), so the answers can be compared with the graph exactly (blind_compare.py).

    python tools/validation_ui/machine_review/blind_check.py payload.b64 triples.pkl --out <workdir> \\
        --dwca <export>/dwca [--pages data/pages_jpg] [--only ids.txt] [--limit N] [--budget 80] [--concurrency 16]

Answers: ``<workdir>/blind_check/answers/<entry_id>.json`` (resumable; calls are cached in
data/cache/blind_check_v1 and logged in its usage.jsonl).
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_payload, write_json  # noqa: E402
from prepare_entries import GraphView, obs_index  # noqa: E402

PRICES = {"gemini-3.7-flash": (0.75, 3.75, 0.075), "gemini-3.8-flash": (0.75, 3.75, 0.075)}   # USD per million: input, output, cached
MARKER = "\n## Entry\n"
DIARIST = "Alfred Laubmann"

INSTRUCTIONS = """# Reading the bird records of one diary entry

You read ONE entry of the ornithological field diaries of Alfred Laubmann (Bavaria and his travels, 1917–1965; handwritten German in Latin cursive with Kurrent elements, and typed or printed inserts: letters, typed reports of other ornithologists, newspaper clippings). You get the scan of the page(s) the entry is written on, in reading order, and then the entry block: the machine transcription of the entry, a numbered list of places, a numbered list of persons, and the records a machine extracted from the entry. The pages may also show the end of the previous entry and the start of the next one: only this entry counts.

The scan decides wherever it is legible; the transcription can be wrong (misread bird names, numbers and places are common). Where the scan is illegible, go by the transcription and give a lower confidence.

Each record line gives only `i` (its index), `name` (the bird name as written) and `passage` (the words the record was taken from). Everything else you state yourself, from the page, for THIS record:

- `here`: false when the entry contains no such observation: the bird is not mentioned, or only in a comparison, an example, a title, a list heading without observation, a negated or hypothetical statement; or the record duplicates an earlier record of the same observation (then the later one is false). An absence ("no Kiebitz seen") is an observation: `here` true, `absent` true.
- `sci` and `de`: the bird the diary means, scientific and modern German name. Old or regional names mean their species (Grünling = Grünfink, Gimpel = Dompfaff, Fischreiher = Graureiher, Weidenlaubvogel = Zilpzalp, Steinkauz). A group name in the diary ("Möwen", "Enten", "Meisen") gets the genus or family, never a species.
- `n`: the number of individuals the text gives for this bird at this place and date, as a string: "1 + 1" = "2", "ein Paar" or "♂♀" = "2", "5 ♂♂ 3 ♀♀" = "8", partial counts of one observation are added up, a range stays a range "6-8", "50 Paare" = "100". null when the text gives no number ("einige", "viele", "ein Flug") or for an absence.
- `absent`: true only when the text says the bird was looked for and NOT there.
- `places`: the numbers of ALL listed places that correctly say where this observation was made: the specific site the passage names (pond, island, street, wood), otherwise the entry's place, and every broader place that contains it (the village, the lake, the area). An empty list when none fits. `site`: the most specific place of the observation in the diary's words when no listed place is that specific, else null.
- `date`: "entry" when the observation is from the day (or within the days) of the entry; the record's own day "YYYY-MM-DD" when the entry quotes an observation of another day ("am 6. IV. hörte ich …"); a year or month "YYYY" / "YYYY-MM" when the text gives no day for it (a remembered breeding season, a literature note); "undated" when the record has no date of its own at all (cumulative species lists, summaries of many years).
- `obs`: who saw or heard the bird: the numbers of the listed persons, or names in `obs_text` for persons not in the list. The diarist (Alfred Laubmann; "ich", "wir" in his own text) for his own observations, with the companions who saw it with him; the reporting person for an observation told or written to him ("nach X", "X meldet", a letter, a pasted typed report; "ich" in a pasted report is its author); the cited author for a literature record. `obs` empty and `obs_text` "unnamed" when a pasted report or letter names no author.
- `type`: "field-observation" (the diarist, with or without companions, observed it), "third-party-report" (someone else told or wrote him) or "literature-record" (from a publication, newspaper, catalogue or collection label).
- `c`: your confidence in this record's values, 0.0–1.0.

Also give the entry's own date and place as its header states them.

## Answer

One JSON object, nothing else.

{"entry": {"date": "YYYY-MM-DD, or YYYY-MM-DD/YYYY-MM-DD for several days", "places": [numbers of the listed places that are the entry's place or contain it], "site": "the entry's place as written when it is not listed, else null", "legible": true | false},
 "records": [{"i": 0, "here": true, "sci": "Anas platyrhynchos", "de": "Stockente", "n": "5", "absent": false, "places": [2, 7], "site": null, "date": "entry", "obs": [1], "obs_text": null, "type": "field-observation", "c": 0.9}]}

Every record index appears exactly once. Keep each record on one line.
"""


def records_of(G: GraphView, s, entry_uid: str) -> list[dict]:
    """The entry's observations in extraction order: index, IRI, written name, passage and what the lists are built from."""
    out, one, label = G.out, G.one, G.label
    recs = []
    for o in out[s].get("containsObservation", []):
        tx = out[o].get("observedTaxon", [None])[0]
        written = one(o, "verbatimIdentification") or (label(tx) if tx is not None else "")
        place = out[o].get("observedAt", [None])[0]
        recs.append({"index": obs_index(o, entry_uid, written), "iri": str(o), "written": written,
                     "passage": one(o, "verbatimNotes"), "locality": one(o, "verbatimLocality"),
                     "place": label(place) if place is not None else "",
                     "observers": [label(p) for p in out[o].get("recordedBy", [])]})
    return sorted(recs, key=lambda r: r["index"])


def unique(values) -> list[str]:
    seen, out = set(), []
    for v in values:
        k = (v or "").strip().casefold()
        if k and k not in seen:
            seen.add(k)
            out.append(v.strip())
    return out


def place_list(G: GraphView, s, recs: list[dict], entry_place: str) -> list[str]:
    travel = []
    for tv in G.out[s].get("containsTravelEvent", []):
        for leg in G.out[tv].get("hasLeg", []):
            for p in ("departurePlace", "arrivalPlace", "viaPlace"):
                travel += [G.label(x) for x in G.out[leg].get(p, [])]
    return unique([entry_place] + [r["locality"] for r in recs] + [r["place"] for r in recs] + travel)


def person_list(G: GraphView, s, recs: list[dict]) -> list[str]:
    mentioned = [G.label(p) for p in G.out[s].get("mentionsPerson", [])]
    return unique([DIARIST] + mentioned + [p for r in recs for p in r["observers"]])


def entry_block(e, recs: list[dict], places: list[str], persons: list[str], n_pages: int) -> str:
    cut = lambda t, n: t if len(t) <= n else t[:n] + " …"   # noqa: E731
    lines = [f"id {e[0]} · volume {e[5]} · {n_pages} page scan(s) above", "", "### Transcription", e[7] or "", "",
             "### Places"]
    lines += [f"{i}: {p}" for i, p in enumerate(places, 1)] or ["(none)"]
    lines += ["", "### Persons"]
    lines += [f"{i}: {p}" + (" (the diarist)" if p == DIARIST else "") for i, p in enumerate(persons, 1)]
    lines += ["", "### Records"]
    lines += [json.dumps({"i": r["index"], "name": r["written"], "passage": cut(r["passage"], 160)}, ensure_ascii=False)
              for r in recs] or ["(none)"]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("payload")
    ap.add_argument("triples")
    ap.add_argument("--out", required=True)
    ap.add_argument("--dwca", required=True, help="the export's dwca/ (only for the record count)")
    ap.add_argument("--pages", default=str(REPO / "data" / "pages_jpg"))
    ap.add_argument("--model", default="gemini-3.7-flash")
    ap.add_argument("--cache", default=str(REPO / "data" / "cache" / "blind_check_v1"))
    ap.add_argument("--budget", type=float, default=80.0, help="stop when the estimated USD of this run reaches it")
    ap.add_argument("--concurrency", type=int, default=16)
    ap.add_argument("--thinking", default="low")
    ap.add_argument("--max-pages", type=int, default=12)
    ap.add_argument("--only", default=None, help="file with entry ids or uids (one per line)")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    work = Path(args.out).resolve() / "blind_check"
    (work / "answers").mkdir(parents=True, exist_ok=True)

    from laubmann_kg.env import load_dotenv
    from laubmann_kg.llm.cache import LLMCache
    from laubmann_kg.llm.clients import build_client
    from laubmann_kg.llm.structured_output import extract_json

    P = load_payload(args.payload)
    E, PG = P["E"], P["PG"]
    print("loading triples …", flush=True)
    G = GraphView(args.triples)
    only = set(Path(args.only).read_text(encoding="utf-8").split()) if args.only else None
    pages = Path(args.pages)

    load_dotenv(REPO / ".env")
    client = build_client(cache=LLMCache(Path(args.cache)), config={
        "backend": "google", "model": args.model, "api_key_env": "GOOGLE_API_KEY", "temperature": 0.0,
        "max_output_tokens": 32768, "timeout": 600, "thinking_level": args.thinking, "context_cache": True,
        "context_cache_marker": MARKER, "media_resolution": "MEDIA_RESOLUTION_HIGH",
        "retry_attempts": 3, "retry_backoff": 2.0})
    p_in, p_out, p_cached = PRICES.get(args.model, PRICES["gemini-3.8-flash"])
    spent = [0.0]
    lock = threading.Lock()

    jobs, skipped = [], collections.Counter()
    for e in E:
        if only is not None and e[0] not in only and e[1] not in only:
            continue
        s = G.entries.get(e[0])
        if s is None or not G.out[s].get("containsObservation"):
            skipped["no record"] += 1
            continue
        out = work / "answers" / f"{e[0]}.json"
        if out.exists():
            skipped["answered"] += 1
            continue
        ids = [PG[i][0] for i in e[8]][:args.max_pages]
        if not any((pages / f"{pid}.jpg").exists() for pid in ids):
            skipped["no page image"] += 1
            continue
        jobs.append((e, s, out, ids))
        if args.limit and len(jobs) >= args.limit:
            break
    print(f"{len(jobs)} entries to check; skipped {dict(skipped)}", flush=True)

    def one(job):
        e, s, out, ids = job
        with lock:
            if spent[0] >= args.budget:
                return "budget"
        images = [(pid, (pages / f"{pid}.jpg").read_bytes()) for pid in ids if (pages / f"{pid}.jpg").exists()]
        recs = records_of(G, s, e[1])
        places = place_list(G, s, recs, e[6] or "")
        persons = person_list(G, s, recs)
        prompt = INSTRUCTIONS + MARKER + entry_block(e, recs, places, persons, len(images))
        try:
            raw = client.complete(prompt, images=images)
        except Exception as exc:  # noqa: BLE001 - one failed entry must not stop the run
            return f"error {str(exc)[:160]}"
        inner = getattr(client, "client", client)
        u = inner.last_usage() if hasattr(inner, "last_usage") else None
        if u:
            cached = u.get("cached_content_token_count", 0)
            cost = ((u.get("prompt_token_count", 0) - cached) * p_in + cached * p_cached
                    + (u.get("candidates_token_count", 0) + u.get("thoughts_token_count", 0)) * p_out) / 1e6
            with lock:
                spent[0] += cost
        try:
            data = extract_json(raw)
        except Exception:  # noqa: BLE001
            data = None
        write_json(out, {"entry_id": e[0], "entry_uid": e[1], "pages": len(images), "model": args.model,
                         "truncated": bool(getattr(raw, "truncated", False)),
                         "records": [{k: r[k] for k in ("index", "iri", "written")} for r in recs],
                         "places": places, "persons": persons,
                         "answer": data if isinstance(data, dict) else None})
        return "ok" if isinstance(data, dict) else "unparseable"

    results: collections.Counter = collections.Counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for i, (job, r) in enumerate(zip(jobs, pool.map(one, jobs)), 1):
            results[r.split(" ")[0]] += 1
            if not r.startswith(("ok", "budget")):
                print(job[0][0], r, flush=True)
            if i % 100 == 0 or i == len(jobs):
                print(f"[{i}/{len(jobs)}] {dict(results)} estimated spend ${spent[0]:.2f}", flush=True)
    print("results", dict(results), f"estimated spend this run ${spent[0]:.2f}", flush=True)


if __name__ == "__main__":
    main()
