"""Record check of every entry: a vision model reads the scan and judges each record of the graph.

The entry dossiers of prepare_entries.py go to Claude subagents and cover a
sample (115 entries of the final graph). This script gives the same material
of EVERY entry to Gemini in one call per entry: the page scans, the
transcription the extraction read, the corrections of the visual reading and
every record the graph holds for the entry (species, count with its range,
locality, georeference, record type, observers, own date, sex, stage,
breeding). The model lists the records that are right by index and, for the
others, the wrong fields with the right values and the words of the page that
show it; records the text states but the graph misses; the entry's date,
place and kind; and the reading corrections that are not right.

A finding is a suggestion for the reviewer (validation UI). ``quote_in_text``
tells whether the quoted words stand in the transcription: then the fix
follows from the text the extraction read (an interpretation error), else it
rests on the model's own reading of the scan.

    python tools/validation_ui/machine_review/record_check.py payload.b64 triples.pkl --out <workdir> \\
        --review <export>/review --dwca <export>/dwca [--pages data/pages_jpg] [--only uids.txt] \\
        [--budget 35] [--concurrency 16] [--merge-only]

Answers: ``<workdir>/record_check/answers/<entry_id>.json`` (resumable; calls
are cached in data/cache/record_check_v1 and logged in its usage.jsonl).
Merged: ``<workdir>/record_check/`` record_checks.csv (the graph_checks.csv
contract of merge.py plus quote, quote_in_text), record_checks_missing.csv,
record_checks_entries.csv, transcript_checks_gemini.csv, summary.json.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_payload, read_json, write_json  # noqa: E402
from prepare_entries import GraphView, graph_records, read_csv  # noqa: E402

PRICES = {"gemini-3.8-flash": (0.75, 3.75, 0.075), "gemini-3.5-flash": (1.5, 9.0, 0.15)}   # USD per million: input, output, cached input
MARKER = "\n## Entry\n"

INSTRUCTIONS = """# Record check of one diary entry

You are checking what a knowledge graph extracted from ONE entry of the ornithological field diaries of Alfred Laubmann (Bavaria and his travels, 1917–1965; handwritten German in Latin cursive with Kurrent elements, and typed or printed inserts). You get the scan of the page(s) the entry is written on, in reading order, and then the entry block: the entry's header as the graph has it, the transcription the extraction read, the corrections a vision model made to that transcription before the extraction, and the records the graph holds for the entry. The pages may also show the end of the previous entry and the start of the next one: only this entry counts.

The scan is the ground truth wherever it is legible; where it is not, judge by the transcription and give a lower confidence. Decide species names from the handwriting: misread bird names are common. Bird names are often underlined on the page.

## The records

One JSON object per line. `i` is the record's index (use it in your answer), `name` the bird name as written, `taxon` and `sci` the species the graph assigned. `n` is the count; `n_range` [min, max] holds a range ("3-5", "80 bis 100") and `n_qual` says how the number is meant (exact, minimum, maximum, approximate, plural-unspecified = "einige", "viele" without a number). A range stored as `n` = its lower bound plus `n_range` is RIGHT. `status` absent = the text says the species was looked for and not found. `loc` is the record's own locality as written when it differs from the entry's place, `place` the place node it was assigned to, `georef` [latitude, longitude, uncertainty in metres] the point published for the record. `type` is field-observation (the diarist's own observation, also with companions), third-party-report (told or written to him: "nach X", "teste Y", "X meldet", letters, pasted reports; "ich" in a pasted report is its author) or literature-record (taken from a publication, newspaper clipping or collection label). `by` are the observers when they are not the diarist alone. `date` is the record's own date when it differs from the entry's. `sex`, `stage`, `breeding` (confirmed, probable, possible), `evidence`, `call`, `behav` and `notes` (the passage the record was taken from) follow the text.

## What to check

1. Every record. Is there such a record in this entry's text? Then: species; count (a missing count is wrong only when the text states one; partial counts of one record add up: "5 + 12 + 150" is 167, so do the sum yourself and compare; a number that belongs to the neighbouring species or is a list number is not the count); locality (which site, pond, lake or village THIS record belongs to; abbreviations of the diarist such as Wb., Nb., Ob., Vkl. keep their meaning); date of the record (a record of another day quoted in the entry carries its own date); observer and record type; sex, life stage and breeding statements. The georeference is wrong only when the point is clearly not the named place: another village of the same name far away, or a country or region centre for a precise site; then give the right place with its district or nearest town in `fix.place` ("Weinhalde bei Kaufbeuren").
   - Right in all these fields, or only trivial issues: put its index in `ok`.
   - `wrong`: name the wrong fields and give the right values in `fix`.
   - `spurious`: there is no such record (a place or a person read as a bird, a negated, hypothetical or comparative statement, a list number read as a count, the same record extracted twice).
   - `unsure`: you cannot decide (illegible, ambiguous).
2. Missing records: species or counts the text of this entry clearly reports that have no record; also persons, travel and weather statements that are missing. Do not list what belongs to the neighbouring entries.
3. The entry's date, place and kind (field-day, species-digest, retrospective, correspondence, other).
4. The reading corrections: list ONLY those that are not right. `partly` = closer than the old text but not exact, or right word but something else changed too; `wrong` = the old text was right, or the new text is another misreading, or it inserts text of another entry; `unclear` = illegible. Give the exact page text in `better` when it is neither the old nor the new text.

Be strict about what counts as wrong: a difference in wording, spelling, capitalisation or underlining is not an error; a value the text does not state is not missing. Every finding needs `quote`: the exact words of the page (as few as prove the point, at most 12) that show the right value, copied letter by letter; when the transcription has these words, copy them as they stand there.

## Answer

One JSON object, nothing else. Free text in German.

{"ok": [indices of the records that are right],
 "findings": [{"i": index, "v": "wrong" | "spurious" | "unsure",
               "fields": ["species" | "count" | "locality" | "georef" | "date" | "observer" | "record_type" | "sex" | "life_stage" | "breeding" | "status" | "other"],
               "fix": {"species_de": "German name", "sci": "scientific name", "count": "5" or "3-5" or "einige", "locality": "as written", "place": "the right place for the georeference", "date": "YYYY-MM-DD", "observer": "names, separated by ;", "record_type": "field-observation | third-party-report | literature-record", "sex": "male | female | mixed", "life_stage": "adult | juvenile | pullus | immature | egg | mixed", "breeding": "confirmed | probable | possible | none", "status": "present | absent", "other": "short"},
               "c": confidence 0.0-1.0, "quote": "words of the page", "why": "one short sentence"}],
 "missing": [{"kind": "observation" | "person" | "travel" | "weather", "text": "the passage", "species_de": "...", "sci": "...", "count": "...", "locality": "...", "date": "YYYY-MM-DD", "observer": "...", "c": confidence}],
 "entry": {"date_ok": true | false, "date": "YYYY-MM-DD when wrong", "place_ok": true | false, "place": "when wrong", "kind_ok": true | false, "kind": "when wrong"},
 "corrections": [{"i": index, "v": "partly" | "wrong" | "unclear", "better": "exact page text"}],
 "legible": true | false}

`fix` holds only the fields you correct. Every record index appears exactly once, in `ok` or in `findings`. Empty lists stay empty lists.
"""

_KEYS = (("written", "name"), ("taxon", "taxon"), ("sci", "sci"), ("count", "n"), ("count_qualifier", "n_qual"), ("status", "status"),
         ("locality", "loc"), ("place", "place"), ("record_type", "type"), ("observers", "by"), ("event_date", "date"), ("sex", "sex"),
         ("life_stage", "stage"), ("breeding", "breeding"), ("evidence", "evidence"), ("call_type", "call"), ("behaviour", "behav"))


def record_line(o: dict) -> str:
    """One observation of graph_records() as the compact line the model reads."""
    r: dict = {"i": o["index"]}
    for src, dst in _KEYS:
        v = o.get(src)
        if v in (None, "", []):
            continue
        if src == "status" and v == "present":
            continue
        if src == "taxon" and v == o.get("written"):
            continue
        r[dst] = int(v) if src == "count" and str(v).isdigit() else v
    if o.get("count_min") or o.get("count_max"):
        r["n_range"] = [int(x) if str(x).isdigit() else x for x in (o.get("count_min"), o.get("count_max"))]
    g = o.get("georef")
    if g and g[1]:
        r["georef"] = [round(float(g[1]), 3), round(float(g[2]), 3)] + ([int(float(g[3]))] if g[3] else [])
    if o.get("notes"):
        r["notes"] = o["notes"][:110]
    return json.dumps(r, ensure_ascii=False, separators=(",", ":"))


def entry_block(e, graph: dict, corrections: list, n_pages: int) -> str:
    """The per-entry part of the prompt (after the cached instructions)."""
    cut = lambda s, n: s if len(s) <= n else s[:n] + " …"   # noqa: E731
    L = [f"id {e[0]} · volume {e[5]} · date in the graph: {e[2] or '—'} (as written: {e[3] or '—'}) · "
         f"place in the graph: {e[6] or '—'} (header: {e[9] or '—'}) · kind: {e[4] or '—'} · {n_pages} page scan(s) above",
         "", "### Transcription (after the reading corrections)", e[7] or "", "",
         "### Reading corrections (i: old → new)"]
    L += [f"{i}: {json.dumps(cut(c['old_text'], 160), ensure_ascii=False)} → {json.dumps(cut(c['new_text'], 160), ensure_ascii=False)}"
          + ("" if c.get("applied") == "y" else " [not applied]") for i, c in enumerate(corrections)] or ["(none)"]
    L += ["", "### Records in the graph"]
    L += [record_line(o) for o in graph["observations"]] or ["(none)"]
    if graph["persons"]:
        L += ["", "### Persons", "; ".join(f"{p['name']} ({', '.join(p['roles'])})" for p in graph["persons"])]
    if graph["travel"]:
        L += ["", "### Travel", "; ".join(f"{t.get('from', '?')} → {t.get('to', '?')}" + (f" ({t['mode']})" if t.get("mode") else "") for t in graph["travel"])]
    if graph["weather"]:
        L += ["", "### Weather", "; ".join(w.get("verbatim", "") for w in graph["weather"])]
    return "\n".join(L)


# ---------------------------------------------------------------- merge
_TAG = re.compile(r"</?[a-zA-Z][^>]*>")


def plain(s: str) -> str:
    return re.sub(r"\s+", " ", _TAG.sub("", s or "")).strip().casefold()


def write_csv(path: Path, fields, rows) -> None:
    with open(path, "w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def merge(work: Path, model: str) -> dict:
    """answers/*.json -> the CSVs and summary.json of the record check."""
    by = f"machine:{model} (scan)"
    rows, missing, entries, tchecks = [], [], [], []
    stats = collections.Counter()
    field_err = collections.Counter()
    for path in sorted((work / "answers").glob("*.json")):
        a = read_json(path)
        ans = a.get("answer") if isinstance(a.get("answer"), dict) else {}
        recs = {r["index"]: r for r in a["records"]}
        occ_counter: collections.Counter = collections.Counter()
        occ_of = {}
        for i in sorted(recs):
            k = recs[i]["written"].lower()
            occ_of[i] = occ_counter[k]
            occ_counter[k] += 1
        text = plain(a.get("text") or "")
        seen: dict = {}
        for i in ans.get("ok") or []:
            if isinstance(i, int) and i in recs:
                seen.setdefault(i, {"v": "ok"})
        for f in ans.get("findings") or []:
            if isinstance(f, dict) and f.get("i") in recs:
                seen[f["i"]] = f
        n = collections.Counter()
        for i in sorted(recs):
            o, f = recs[i], seen.get(i)
            v = ((f or {}).get("v") or "unchecked").lower() if f else "unchecked"
            if v not in ("ok", "wrong", "spurious", "unsure"):
                v = "unsure"
            if not f:
                v = "unchecked"
            n[v] += 1
            stats[f"obs {v}"] += 1
            fields = [x for x in (f or {}).get("fields") or [] if isinstance(x, str)]
            if v == "wrong":
                for x in fields:
                    field_err[x] += 1
            if v in ("ok", "unchecked"):
                rows.append({"entry_id": a["entry_id"], "entry_uid": a["entry_uid"], "obs_index": i, "occurrence": occ_of[i],
                             "written": o["written"], "taxon": o.get("taxon", ""), "sci": o.get("sci", ""), "count": o.get("count", ""),
                             "verdict": v, "reviewed_by": by})
                continue
            fix = {k: x for k, x in (f.get("fix") or {}).items() if x not in (None, "")} if isinstance(f.get("fix"), dict) else {}
            quote = f.get("quote") if isinstance(f.get("quote"), str) else ""
            try:
                conf = max(0.0, min(1.0, float(f.get("c"))))
            except (TypeError, ValueError):
                conf = 0.0
            rows.append({"entry_id": a["entry_id"], "entry_uid": a["entry_uid"], "obs_index": i, "occurrence": occ_of[i],
                         "written": o["written"], "taxon": o.get("taxon", ""), "sci": o.get("sci", ""), "count": o.get("count", ""),
                         "verdict": v, "fields": ";".join(fields), "correction": json.dumps(fix, ensure_ascii=False) if fix else "",
                         "confidence": f"{conf:.2f}", "reason": f.get("why") or "", "quote": quote,
                         "quote_in_text": "y" if quote and plain(quote) in text else "n", "reviewed_by": by})
        for m in ans.get("missing") or []:
            if not isinstance(m, dict):
                continue
            stats[f"missing {m.get('kind', '?')}"] += 1
            missing.append({"entry_id": a["entry_id"], "entry_uid": a["entry_uid"], "kind": m.get("kind"), "text": m.get("text"),
                            "species_de": m.get("species_de"), "sci": m.get("sci"), "count": m.get("count"), "locality": m.get("locality"),
                            "date": m.get("date"), "observer": m.get("observer"), "confidence": m.get("c"),
                            "text_in_entry": "y" if m.get("text") and plain(str(m["text"])) in text else "n", "reviewed_by": by})
        ef = ans.get("entry") if isinstance(ans.get("entry"), dict) else {}
        for k in ("date_ok", "place_ok", "kind_ok"):
            if ef.get(k) is False:
                stats[f"entry {k} false"] += 1
        entries.append({"entry_id": a["entry_id"], "entry_uid": a["entry_uid"], "n_obs": len(recs), "ok": n["ok"], "wrong": n["wrong"],
                        "spurious": n["spurious"], "unsure": n["unsure"], "unchecked": n["unchecked"],
                        "missing": len(ans.get("missing") or []), "date_ok": ef.get("date_ok"), "date": ef.get("date") if ef.get("date_ok") is False else "",
                        "place_ok": ef.get("place_ok"), "place": ef.get("place") if ef.get("place_ok") is False else "",
                        "kind_ok": ef.get("kind_ok"), "kind": ef.get("kind") if ef.get("kind_ok") is False else "",
                        "scan_legible": ans.get("legible"), "truncated": "y" if a.get("truncated") else "", "pages": a.get("pages")})
        stats["entries"] += 1
        stats["entries truncated"] += bool(a.get("truncated"))
        stats["entries unparseable"] += not ans
        corr = a.get("corrections") or []
        for c in ans.get("corrections") or []:
            if isinstance(c, dict) and isinstance(c.get("i"), int) and 0 <= c["i"] < len(corr):
                old, new, applied = corr[c["i"]]
                v = (c.get("v") or "").lower()
                if v in ("partly", "wrong", "unclear"):
                    stats[f"correction {v}"] += 1
                    tchecks.append({"entry_uid": a["entry_uid"], "entry_id": a["entry_id"], "old_text": old, "new_text": new, "applied": applied,
                                    "verdict": v, "better_text": c.get("better") or "", "reviewed_by": by})
        stats["corrections seen"] += len(corr)
    write_csv(work / "record_checks.csv", ["entry_id", "entry_uid", "obs_index", "occurrence", "written", "taxon", "sci", "count", "verdict",
                                           "fields", "correction", "confidence", "reason", "quote", "quote_in_text", "reviewed_by"], rows)
    write_csv(work / "record_checks_missing.csv", ["entry_id", "entry_uid", "kind", "text", "species_de", "sci", "count", "locality", "date",
                                                   "observer", "confidence", "text_in_entry", "reviewed_by"], missing)
    write_csv(work / "record_checks_entries.csv", ["entry_id", "entry_uid", "n_obs", "ok", "wrong", "spurious", "unsure", "unchecked", "missing",
                                                   "date_ok", "date", "place_ok", "place", "kind_ok", "kind", "scan_legible", "truncated", "pages"], entries)
    write_csv(work / "transcript_checks_gemini.csv", ["entry_uid", "entry_id", "old_text", "new_text", "applied", "verdict", "better_text",
                                                      "reviewed_by"], tchecks)
    summary = {"model": model, "stats": dict(stats), "wrong_fields": dict(field_err.most_common())}
    write_json(work / "summary.json", summary)
    return summary


# ---------------------------------------------------------------- run
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("payload")
    ap.add_argument("triples")
    ap.add_argument("--out", required=True)
    ap.add_argument("--pages", default=str(REPO / "data" / "pages_jpg"), help="folder of <page_id>.jpg (tools/export_page_images.py)")
    ap.add_argument("--review", required=True, help="the export's review/ (transcript_corrections.csv)")
    ap.add_argument("--dwca", required=True, help="the export's dwca/ (occurrence.txt)")
    ap.add_argument("--model", default="gemini-3.8-flash")
    ap.add_argument("--cache", default=str(REPO / "data" / "cache" / "record_check_v1"))
    ap.add_argument("--budget", type=float, default=35.0, help="stop when the estimated USD of this run reaches it")
    ap.add_argument("--concurrency", type=int, default=16)
    ap.add_argument("--thinking", default="low", help="minimal | low | medium | high")
    ap.add_argument("--max-pages", type=int, default=12)
    ap.add_argument("--min-chars", type=int, default=60, help="entries with fewer characters and no record are skipped")
    ap.add_argument("--only", default=None, help="file with entry uids or ids (one per line): check only these")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--merge-only", action="store_true")
    args = ap.parse_args()
    work = Path(args.out).resolve() / "record_check"
    (work / "answers").mkdir(parents=True, exist_ok=True)
    if args.merge_only:
        print(json.dumps(merge(work, args.model), ensure_ascii=False, indent=1))
        return

    from laubmann_kg.env import load_dotenv
    from laubmann_kg.llm.cache import LLMCache
    from laubmann_kg.llm.clients import build_client
    from laubmann_kg.llm.structured_output import extract_json

    P = load_payload(args.payload)
    E, PG = P["E"], P["PG"]
    print("loading triples …", flush=True)
    G = GraphView(args.triples)
    corr = collections.defaultdict(list)
    for r in read_csv(Path(args.review) / "transcript_corrections.csv"):
        corr[r["entry_uid"]].append(r)
    occ_rows = {r["occurrenceID"]: r for r in read_csv(Path(args.dwca) / "occurrence.txt", "\t")}
    only = set(Path(args.only).read_text(encoding="utf-8").split()) if args.only else None
    pages = Path(args.pages)

    load_dotenv(REPO / ".env")                     # GOOGLE_API_KEY
    client = build_client(cache=LLMCache(Path(args.cache)), config={
        "backend": "google", "model": args.model, "api_key_env": "GOOGLE_API_KEY", "temperature": 0.0,
        "max_output_tokens": 32768, "timeout": 600, "thinking_level": args.thinking, "context_cache": True,
        "context_cache_marker": MARKER, "media_resolution": "MEDIA_RESOLUTION_HIGH",
        "retry_attempts": 3, "retry_backoff": 2.0})
    p_in, p_out, p_cached = PRICES.get(args.model, PRICES["gemini-3.8-flash"])
    spent = [0.0]
    lock = threading.Lock()

    jobs = []
    skipped = collections.Counter()
    for e in E:
        if only is not None and e[0] not in only and e[1] not in only:
            continue
        s = G.entries.get(e[0])
        if s is None:
            skipped["not in graph"] += 1
            continue
        out = work / "answers" / f"{e[0]}.json"
        if out.exists():
            skipped["answered"] += 1
            continue
        if not G.out[s].get("containsObservation") and len(e[7] or "") < args.min_chars:
            skipped["no record, short text"] += 1
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
        graph = graph_records(G, s, e[1], e[2], occ_rows)
        cs = corr.get(e[1], [])
        prompt = INSTRUCTIONS + MARKER + entry_block(e, graph, cs, len(images))
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
        write_json(out, {"entry_id": e[0], "entry_uid": e[1], "pages": len(images), "truncated": bool(getattr(raw, "truncated", False)),
                         "records": [{k: o.get(k) for k in ("index", "written", "taxon", "sci", "count") if o.get(k) is not None}
                                     for o in graph["observations"]],
                         "corrections": [[c["old_text"], c["new_text"], c.get("applied", "")] for c in cs],
                         "text": e[7] or "", "answer": data if isinstance(data, dict) else None})
        return "ok" if isinstance(data, dict) else "unparseable"

    results: collections.Counter = collections.Counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for i, (job, r) in enumerate(zip(jobs, pool.map(one, jobs)), 1):
            results[r.split(" ")[0]] += 1
            if not r.startswith(("ok", "budget")):
                print(job[0][0], r, flush=True)
            if i % 100 == 0 or i == len(jobs):
                print(f"[{i}/{len(jobs)}] {dict(results)} estimated spend ${spent[0]:.2f}", flush=True)
    print("results", dict(results), f"estimated spend this run ${spent[0]:.2f} (cache hits cost nothing)", flush=True)
    print(json.dumps(merge(work, args.model), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
