"""Attribution check: who observed the records the graph credits to the diarist?

The extraction reads "ich" in a pasted report as the diarist when the report
does not name its author on the spot: Walter Wüst's numbered
"Speichersee-Begehung" reports, Einhard Bezzel's and Werner Rathmayer's typed
sheets and letters, transcribed as part of the entry, carry Alfred Laubmann as
observer and field-observation as record type (blind scan audit of 2026-10-03,
docs/corpus_tiers.md). The same reports are often attributed right in one entry
and wrong in the next.

This script asks, for every entry with records credited to the diarist and a
sign of a pasted report (text signals below), who made each of those records.
Two judges answer independently from the page scans, the entry's text, the end
of the previous entry (where the diarist writes "X schickt mir die
nachfolgenden Berichte:") and the records: Gemini (``run``) and Claude
subagents (``dossiers`` writes their material; the agents write answers in the
same format). ``merge`` keeps what both agree on and writes
``attribution_machine.csv`` in the contract of
``review/observation_corrections.csv`` (fields record_type, observer,
co_observers; confidence 1 - (1 - c1)(1 - c2) as in record_check_combine.py, agreement = 2), applied by the
pipeline through ``review.machine.attribution``.

    python tools/validation_ui/machine_review/attribution_check.py candidates triples.pkl --export <export> --corpus data/corpus_patched --out <work>
    python tools/validation_ui/machine_review/attribution_check.py pages --out <work> --pages data/pages_jpg --drive-pages drive_pages.json
    python tools/validation_ui/machine_review/attribution_check.py run triples.pkl --export <export> --corpus data/corpus_patched --out <work> [--budget 10]
    python tools/validation_ui/machine_review/attribution_check.py dossiers triples.pkl --export <export> --corpus data/corpus_patched --out <work> [--only ids.txt]
    python tools/validation_ui/machine_review/attribution_check.py merge --out <work> [--csv data/review/machine/attribution_machine.csv]

Work folder: candidates.csv, gemini/<entry_id>.json, claude/dossiers/<entry_id>.json (+ pages), claude/answers/<entry_id>.json,
attribution_judgements.csv (every record both judges saw, with both verdicts), summary.json.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sys
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO / "tools" / "validation_ui" / "graph_check"))
from prepare_entries import GraphView, graph_records, read_csv  # noqa: E402

csv.field_size_limit(10 ** 9)
DIARIST = "Alfred Laubmann"
PRICES = {"gemini-3.8-flash": (0.75, 3.75, 0.075)}   # USD per million: input, output, cached input
MARKER = "\n## Entry\n"
MAX_PAGES = 6

# ---------------------------------------------------------------- candidates
TAG = re.compile(r"</?[a-zA-Z][^>]*>")
SPLIT_ENTRY = re.compile(r"e\d{4}[a-z]$")
TYPED_ITEM = re.compile(r"(?:^|\s)\d{1,3}\)\s?[A-ZÄÖÜ][a-zäöüß]+[,;:]")
SECTION_TERMS = re.compile(r"\b(Wb|Vkl|Ob|Ft|Hb|Ob\.|Wb\.|Vkl\.|Ft\.|SD|QD|E-Werk|Querdamm|Süddamm|Norddamm|Westbecken|Ostbecken|Begehung|Sps)\b")
REPORT_WORDS = re.compile(r"Speichersee.?Begehung|Sps\.?-?Begehung|Bericht|berichtet|schreibt|schickt|sendet|Brief|Karte vom|Abschrift|"
                          r"Durchschlag|Mit (?:herzlichen|besten|freundlichen) Grü|Dein |Ihr |gez\.|Ismaninger Teichgebiet", re.I)
CAPS = re.compile(r"\b[A-ZÄÖÜ]{4,}\b")
WIND = {"NNO", "SSW", "WSW", "ONO", "OSO", "WNW", "NNW", "SSO", "UHR"}
COLON_LIST = re.compile(r"(?:^|[.\n]\s*)[A-ZÄÖÜ][a-zäöüß]+(?:[- ][A-Za-zäöüß]+)?:\s", re.M)
WEEKDAY = re.compile(r"\b(?:So|Mo|Di|Die|Mi|Do|Fr|Sa)\.\s?\d{1,2}\.\s?[IVX]+\.\s?(?:19)?\d{2}")
TIME_RANGE = re.compile(r"\d{1,2}[.:]?\d{0,2}\s?(?:-|bis)\s?\d{1,2}[.:]\d{2}\s?(?:Uhr|h)\b")
COMPACT_HEAD = re.compile(r"^\W*\d{1,2}\.\s?(?:[A-Z][a-zä]{2,4}|[IVX]+)\.\s?\d{2}\.")
ABBR_UP = re.compile(r"\b(?:SD|ND|QD|OB|WB|VKL|FT|GS|WT|MW)\b")


def report_signals(entry_id: str, text: str, passages: list[str], boundary_kind: str, kind: str, context_before: str) -> list[str]:
    """Signs that an entry holds a report or letter of somebody else (any one makes it a candidate)."""
    s = []
    if boundary_kind == "correspondence":
        s.append("boundary-correspondence")      # the entry-boundary review called it a report
    if kind == "correspondence":
        s.append("kind-correspondence")
    if SPLIT_ENTRY.search(entry_id):
        s.append("split")                        # separately dated part of a page (reports, inserts)
    if context_before:
        s.append("context-before")
    if len(TYPED_ITEM.findall(" " + text)) >= 5:
        s.append("typed-list")
    if any(SECTION_TERMS.search(p) for p in passages):
        s.append("ismaning-terms")
    if len([w for w in CAPS.findall(text) if w not in WIND]) >= 2:
        s.append("caps-names")                   # typed reports write names in capitals
    if len(COLON_LIST.findall(text)) >= 5:
        s.append("species-colon-list")
    if WEEKDAY.search(text) or TIME_RANGE.search(text):
        s.append("weekday-time-head")
    if COMPACT_HEAD.search(text):
        s.append("compact-date-head")
    if len(ABBR_UP.findall(text)) >= 3:
        s.append("report-abbreviations")
    if re.search(r"\b[Mm]it [Hh]einz\b", text):
        s.append("mit-heinz")
    if REPORT_WORDS.search(text):
        s.append("report-words")
    return s


def corpus_rows(corpus: Path) -> list[dict]:
    return read_csv(corpus / "entries.csv")


def entry_pages(row: dict) -> list[str]:
    try:
        regions = json.loads(row.get("source_regions") or "[]")
    except ValueError:
        regions = []
    out = []
    for r in regions:
        pid = r.get("page_id")
        if pid and pid not in out:
            out.append(pid)
    if not out and row.get("page_id"):
        out.append(row["page_id"])
    return out[:MAX_PAGES]


def diarist_only(o: dict) -> bool:
    """A record the graph credits to the diarist (his own field observation, alone or with companions)."""
    return (o.get("record_type", "field-observation") == "field-observation"
            and (not o.get("observers") or DIARIST in o["observers"]))


def companions(o: dict) -> list[str]:
    return [p for p in (o.get("observers") or []) if p != DIARIST]


def load_world(triples, export, corpus):
    print("loading triples …", flush=True)
    G = GraphView(triples)
    occ = {r["occurrenceID"]: r for r in read_csv(Path(export) / "dwca" / "occurrence.txt", "\t")}
    rows = corpus_rows(Path(corpus))
    return G, occ, rows


def cmd_candidates(a) -> None:
    G, occ, rows = load_world(a.triples, a.export, a.corpus)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stats = collections.Counter()
    with open(out / "candidates.csv", "w", encoding="utf-8", newline="") as h:
        w = csv.writer(h)
        w.writerow(["entry_id", "entry_uid", "n_records", "n_diarist", "signals", "pages"])
        for row in rows:
            s = G.entries.get(row["entry_id"])
            if s is None:
                continue
            graph = graph_records(G, s, row["entry_uid"], G.one(s, "eventDate"), occ)
            own = [o for o in graph["observations"] if diarist_only(o)]
            if not own:
                continue
            text = TAG.sub("", G.one(s, "fieldNotes") or row.get("text_clean", ""))
            sig = report_signals(row["entry_id"], text, [TAG.sub("", o.get("notes", "")) for o in own], row.get("boundary_kind", ""),
                                 G.one(s, "entryKind"), row.get("context_before", ""))
            if not sig:
                continue
            stats["entries"] += 1
            stats["records"] += len(own)
            for x in sig:
                stats[x] += 1
            w.writerow([row["entry_id"], row["entry_uid"], len(graph["observations"]), len(own), " ".join(sig), " ".join(entry_pages(row))])
    print(json.dumps(stats, indent=1))


def cmd_pages(a) -> None:
    """Fetch the page scans of the candidates (Drive thumbnails, 2000 px JPEG) into --pages."""
    from io import BytesIO

    from PIL import Image
    drive = json.loads(Path(a.drive_pages).read_text(encoding="utf-8"))
    pages = Path(a.pages)
    pages.mkdir(parents=True, exist_ok=True)
    want = []
    for r in read_csv(Path(a.out) / "candidates.csv"):
        for pid in r["pages"].split():
            if pid not in want and not (pages / f"{pid}.jpg").exists():
                want.append(pid)
    print(len(want), "pages to fetch", flush=True)

    def one(pid):
        fid = drive.get(pid)
        if not fid:
            return "no drive id"
        for _ in range(3):
            try:
                data = urllib.request.urlopen(f"https://drive.google.com/thumbnail?id={fid}&sz=w2000", timeout=60).read()
                im = Image.open(BytesIO(data)).convert("RGB")
                im.thumbnail((2000, 2000))
                tmp = pages / f"{pid}.tmp"
                im.save(tmp, "JPEG", quality=85)
                tmp.replace(pages / f"{pid}.jpg")
                return "ok"
            except Exception as exc:  # noqa: BLE001
                err = str(exc)[:80]
        return "error " + err

    res = collections.Counter()
    with ThreadPoolExecutor(max_workers=12) as pool:
        for i, r in enumerate(pool.map(one, want), 1):
            res[r.split(" ")[0]] += 1
            if i % 200 == 0:
                print(i, dict(res), flush=True)
    print(dict(res))


# ---------------------------------------------------------------- the question
INSTRUCTIONS = """# Who observed these records?

You are checking ONE entry of the ornithological field diaries of Alfred Laubmann (München and Bavaria, 1917–1965; his own notes are handwritten German). Laubmann also copied or pasted other people's reports and letters into the diary: typed or handwritten sheets by Walter Wüst (his numbered "Speichersee-Begehung" reports from the Ismaninger Teichgebiet, letters signed "Dein Walter" / "Walther"), Einhard Bezzel, Werner Rathmayer (often "Mit Heinz", i.e. with Heinz Remold), Adolf Müller and others. Often his own day note ends with "X schickt mir die nachfolgenden Berichte:" and the report follows, in the same entry or as the next entry. In such a report "ich", "wir", "mit Heinz" are its AUTHOR, not Laubmann.

A knowledge graph extracted the entry and credits the records listed below to Laubmann as his own field observations. Decide for each of these records who actually made it.

You get: the page scan(s) the entry is written on (in reading order; they may also show neighbouring entries — only this entry counts, but a heading, cover note or signature on the page may tell you who wrote it), the end of the previous entry and the start of the next one, the entry's text as transcribed, and the records (`i` = index, `name` = bird name as written, `notes` = the passage it was taken from).

For every listed record choose:
- `diarist`: Laubmann's own observation (his own handwritten field notes, also when companions were with him).
- another person: the record comes from somebody else's report, letter or notes pasted or copied into the diary, or the text says another person saw it ("Wüst meldet", "nach Bezzel"). Give the person's name as the page, the entry, the cover note or the signature gives it (full name when the diary gives one, e.g. "Walter Wüst", "Werner Rathmayer", "Einhard Bezzel"); `null` when it is clearly not Laubmann's own observation but the author cannot be determined. Do not guess a name: name a person only when the page or the neighbouring text says who wrote or observed it, or when the report belongs to a series whose author the diary names (Wüst's numbered "Speichersee-Begehung" reports).
- record type: `third-party-report` for somebody else's observation, `literature-record` when copied from a publication or collection label.

Signs of a pasted report: typewriter text; a heading of its own (date with weekday, time span "9 - 17.45 Uhr", "531. Speichersee-Begehung", "Ismaninger Teichgebiet"); names in CAPITALS; "Art: Bemerkung" lists; abbreviations of the Ismaning ponds (Wb, Ob, Vkl, SD, ND, QD, FT); a greeting or signature; a cover note before it. Laubmann's own notes start with "Tag. Monat Jahr. Ort." in his hand. Be careful in both directions: Laubmann himself went to Ismaning many times and also wrote about the ponds, and a report is not always typed.

## Answer

One JSON object, nothing else. Free text in German, short.

{"report": "none" | "part" | "all",          // does this entry contain a report or letter of somebody else? all = the whole entry is one
 "author": "name or null",                    // the author of that report, if any
 "evidence": "the words of the page that show who wrote it (at most 15), or null",
 "diarist": [indices of records that are Laubmann's own],
 "others": [{"i": [indices], "by": "name or null", "type": "third-party-report" | "literature-record", "c": confidence 0.0-1.0, "why": "one short sentence"}]}

Every listed index appears exactly once, in `diarist` or in one group of `others`. Group records with the same observer and type together.
"""


def entry_block(row: dict, G, s, own: list[dict], prev_text: str, next_text: str, n_pages: int, persons: list) -> str:
    text = TAG.sub("", G.one(s, "fieldNotes") or row.get("text_clean", ""))
    L = [f"id {row['entry_id']} · date {G.one(s, 'eventDate') or row.get('date_norm') or '—'} · place {row.get('location_raw') or '—'} · "
         f"kind in the graph: {G.one(s, 'entryKind') or '—'} · {n_pages} page scan(s) above", ""]
    if row.get("context_before"):
        L += ["### Heading the entry belongs to", row["context_before"], ""]
    L += ["### End of the previous entry", ("… " + prev_text[-500:]) if prev_text else "(none)", "",
          "### Text of this entry", text, "", "### Start of the next entry", (next_text[:250] + " …") if next_text else "(none)", ""]
    if persons:
        L += ["### Persons the graph found in the entry", "; ".join(f"{p['name']} ({', '.join(p['roles'])})" for p in persons), ""]
    L += ["### Records credited to Laubmann"]
    for o in own:
        r = {"i": o["index"], "name": o.get("written")}
        if o.get("count"):
            r["n"] = o["count"]
        if o.get("locality"):
            r["loc"] = o["locality"]
        if companions(o):
            r["with"] = companions(o)
        if o.get("notes"):
            r["notes"] = TAG.sub("", o["notes"])[:160]
        L.append(json.dumps(r, ensure_ascii=False, separators=(",", ":")))
    return "\n".join(L)


def build_jobs(a, G, occ, rows, only=None):
    pos = {r["entry_id"]: i for i, r in enumerate(rows)}
    text_of = lambda r: TAG.sub("", (G.one(G.entries[r["entry_id"]], "fieldNotes") if r["entry_id"] in G.entries else "")   # noqa: E731
                                or r.get("text_clean", ""))
    cands = read_csv(Path(a.out) / "candidates.csv")
    jobs = []
    for c in cands:
        if only is not None and c["entry_id"] not in only:
            continue
        row = rows[pos[c["entry_id"]]]
        s = G.entries[c["entry_id"]]
        graph = graph_records(G, s, row["entry_uid"], G.one(s, "eventDate"), occ)
        own = [o for o in graph["observations"] if diarist_only(o)]
        i = pos[c["entry_id"]]
        prev = rows[i - 1] if i > 0 and rows[i - 1]["volume"] == row["volume"] else None
        nxt = rows[i + 1] if i + 1 < len(rows) and rows[i + 1]["volume"] == row["volume"] else None
        jobs.append({"row": row, "s": s, "own": own, "graph": graph, "pages": c["pages"].split(),
                     "prev": text_of(prev) if prev else "", "next": text_of(nxt) if nxt else ""})
    return jobs


def cmd_run(a) -> None:
    from laubmann_kg.env import load_dotenv
    from laubmann_kg.llm.cache import LLMCache
    from laubmann_kg.llm.clients import build_client
    from laubmann_kg.llm.structured_output import extract_json

    G, occ, rows = load_world(a.triples, a.export, a.corpus)
    only = set(Path(a.only).read_text(encoding="utf-8").split()) if a.only else None
    work = Path(a.out) / "gemini"
    work.mkdir(parents=True, exist_ok=True)
    pages = Path(a.pages)
    jobs = [j for j in build_jobs(a, G, occ, rows, only) if not (work / f"{j['row']['entry_id']}.json").exists()]
    if a.limit:
        jobs = jobs[:a.limit]
    print(len(jobs), "entries to judge", flush=True)
    load_dotenv(REPO / ".env")
    client = build_client(cache=LLMCache(Path(a.cache)), config={
        "backend": "google", "model": a.model, "api_key_env": "GOOGLE_API_KEY", "temperature": 0.0,
        "max_output_tokens": 16384, "timeout": 600, "thinking_level": "low", "context_cache": True,
        "context_cache_marker": MARKER, "media_resolution": "MEDIA_RESOLUTION_HIGH", "retry_attempts": 3, "retry_backoff": 2.0})
    p_in, p_out, p_cached = PRICES.get(a.model, PRICES["gemini-3.8-flash"])
    spent = [0.0]
    lock = threading.Lock()

    def one(j):
        with lock:
            if spent[0] >= a.budget:
                return "budget"
        images = [(pid, (pages / f"{pid}.jpg").read_bytes()) for pid in j["pages"] if (pages / f"{pid}.jpg").exists()]
        prompt = INSTRUCTIONS + MARKER + entry_block(j["row"], G, j["s"], j["own"], j["prev"], j["next"], len(images), j["graph"]["persons"])
        try:
            raw = client.complete(prompt, images=images)
        except Exception as exc:  # noqa: BLE001
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
        (work / f"{j['row']['entry_id']}.json").write_text(json.dumps(
            {"entry_id": j["row"]["entry_id"], "entry_uid": j["row"]["entry_uid"], "pages": len(images),
             "records": [o["index"] for o in j["own"]], "answer": data if isinstance(data, dict) else None},
            ensure_ascii=False, indent=1), encoding="utf-8")
        return "ok" if isinstance(data, dict) else "unparseable"

    res = collections.Counter()
    with ThreadPoolExecutor(max_workers=a.concurrency) as pool:
        for i, (j, r) in enumerate(zip(jobs, pool.map(one, jobs)), 1):
            res[r.split(" ")[0]] += 1
            if not r.startswith(("ok", "budget")):
                print(j["row"]["entry_id"], r, flush=True)
            if i % 100 == 0 or i == len(jobs):
                print(f"[{i}/{len(jobs)}] {dict(res)} ${spent[0]:.2f}", flush=True)
    print("results", dict(res), f"spend ${spent[0]:.2f}")


CLAUDE_TASK = """# Attribution check — instructions for one batch

{instructions}

## How to work

Your batch is `{root}/claude/batches/batch_NN.txt` (NN = the number you were given): one entry id per line. For each entry id X:
1. Read `{root}/claude/dossiers/X.json`: `block` is the entry material exactly as described above (heading, end of the previous entry, text, start of the next entry, persons, records credited to Laubmann), `pages` the page scans in reading order.
2. Look at every page image of `pages` ONCE with the Read tool.
3. Write `{root}/claude/answers/X.json` with the answer object described above (only that JSON).

Work carefully but do not over-deliberate; use no other tools than Read and Write, and write nothing else anywhere. When all entries of the batch are done, reply with one line: `batch NN: n entries, k with records of others`.
"""


def cmd_dossiers(a) -> None:
    G, occ, rows = load_world(a.triples, a.export, a.corpus)
    only = set(Path(a.only).read_text(encoding="utf-8").split()) if a.only else None
    root = Path(a.out).resolve()
    d = root / "claude" / "dossiers"
    d.mkdir(parents=True, exist_ok=True)
    (root / "claude" / "answers").mkdir(parents=True, exist_ok=True)
    (root / "claude" / "batches").mkdir(parents=True, exist_ok=True)
    pages = Path(a.pages).resolve()
    ids = []
    for j in build_jobs(a, G, occ, rows, only):
        imgs = [str(pages / f"{p}.jpg") for p in j["pages"] if (pages / f"{p}.jpg").exists()]
        block = entry_block(j["row"], G, j["s"], j["own"], j["prev"], j["next"], len(imgs), j["graph"]["persons"])
        (d / f"{j['row']['entry_id']}.json").write_text(json.dumps({"entry_id": j["row"]["entry_id"], "pages": imgs, "block": block},
                                                                     ensure_ascii=False, indent=1), encoding="utf-8")
        ids.append((j["row"]["entry_id"], len(j["own"]), len(imgs)))
    # batches of about a.batch_records records and at most a.batch_entries entries
    batches, cur, load = [], [], 0
    for eid, n, _ in ids:
        if cur and (load + n > a.batch_records or len(cur) >= a.batch_entries):
            batches.append(cur); cur, load = [], 0
        cur.append(eid); load += n
    if cur:
        batches.append(cur)
    for i, b in enumerate(batches, 1):
        (root / "claude" / "batches" / f"batch_{i:02d}.txt").write_text("\n".join(b) + "\n", encoding="utf-8")
    (root / "claude" / "INSTRUCTIONS.md").write_text(CLAUDE_TASK.format(instructions=INSTRUCTIONS, root=root), encoding="utf-8")
    print(f"{len(ids)} dossiers, {len(batches)} batches in {root / 'claude'}")


# ---------------------------------------------------------------- merge
def verdicts(answer: dict | None, indices: list[int]) -> dict[int, tuple]:
    """{index: ("diarist",) | ("other", name or None, type, confidence, why)} of one judge's answer."""
    out: dict[int, tuple] = {}
    if not isinstance(answer, dict):
        return out
    for i in answer.get("diarist") or []:
        if isinstance(i, int):
            out[i] = ("diarist",)
    for g in answer.get("others") or []:
        if not isinstance(g, dict):
            continue
        idx = g.get("i")
        idx = idx if isinstance(idx, list) else [idx]
        typ = g.get("type") if g.get("type") in ("third-party-report", "literature-record") else "third-party-report"
        by = (g.get("by") or "").strip() or None
        if by and by.casefold().strip(". ") in ("laubmann", "alfred laubmann", "a. laubmann", "diarist", "ich"):
            for i in idx:
                if isinstance(i, int):
                    out[i] = ("diarist",)
            continue
        try:
            c = float(g.get("c", 0.0))
        except (TypeError, ValueError):
            c = 0.0
        for i in idx:
            if isinstance(i, int):
                out[i] = ("other", by, typ, c, (g.get("why") or "")[:200])
    return {i: v for i, v in out.items() if i in indices}


def surname(name: str | None) -> str:
    if not name:
        return ""
    n = re.sub(r"\(.*?\)", "", name)
    toks = [t for t in re.findall(r"[A-Za-zÄÖÜäöüß]+", n) if t.casefold() not in ("dr", "herr", "hr", "prof", "freund", "frau", "frl")]
    if not toks:
        return ""
    s = toks[-1].casefold()
    for x, y in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(x, y)
    return s


NAME = r"((?:(?:Dr|Herr|Hr|Freund|Frl|Frau)\.?\s+)?(?:[A-ZÄÖÜ][a-zäöüß]+\.?\s+|[A-ZÄÖÜ]\.\s?){0,2}[A-ZÄÖÜ][a-zäöüß]{2,})"
COVER_NOTE = [re.compile(NAME + r",?(?:\s+[A-ZÄÖÜ][a-zäöüß]+,)?\s+(?:schickt|sendet|sandte|übermittelt|gibt|bringt|teilt)\s+mir\b[^.:]{0,120}?(?:Bericht|Beobachtung|Aufzeichnung|Liste)"),
              re.compile(r"(?:Bericht|Berichte|Aufzeichnungen|Beobachtungen)\s+(?:von|des|aus [A-ZÄÖÜ][a-zäöüß]+ von)\s+(?:Freund\s+|Herrn\s+)?" + NAME),
              re.compile(r"(?:gez\.|Unterschrift:?)\s*" + NAME),
              re.compile(r"Bericht\s+" + NAME + r"(?:'s|s)\b")]
MONTHS = {"januar", "jaenner", "februar", "maerz", "april", "mai", "juni", "juli", "august", "september", "oktober", "october",
          "november", "dezember", "december", "ismaning", "muenchen"}
WUEST_SERIES = re.compile(r"\b\d{3}\.\s?(?:Speichersee|Sps\.?)\s?-?\s?Begehung")


def text_authors(prev_tail: str, text: str) -> set[str]:
    """Surnames the diary itself gives as the author of what follows: a cover note at the end of the
    previous entry or the start of this one ("Werner Rathmayer schickt mir nachfolgende Berichte:",
    "Bericht von E. Bezzel"), a signature ("gez. Heinz Remold"), or Wüst's numbered series
    ("531. Speichersee-Begehung", signed "Dein Walter" where it is signed)."""
    out = set()
    for chunk in (prev_tail[-400:], text[:400], text[-300:]):
        for rx in COVER_NOTE:
            for m in rx.finditer(chunk):
                out.add(surname(m.group(1)))
    if WUEST_SERIES.search(text):
        out.add("wuest")
    return {x for x in out if x and x != "laubmann" and x not in MONTHS}


def entry_spelling(name: str, persons: list[str]) -> str:
    """The spelling the graph already uses for this person in the entry (one person of the entry with
    the same surname and fitting first names or initials), so entity resolution puts the record with
    that person ("Chr. D. Erdt", not a second node "Chr. Erdt"; never the old label "Heinrich Wüst" for
    "Walter Wüst"); else ``name``."""
    from laubmann_kg.resolution.persons import _parts, person_key

    def given(n):                      # first names and initials ("chr", "d")
        init, firsts, _ = _parts(person_key(n))
        return firsts + init

    def fits(a, b):                    # every given name of the shorter list starts a given name of the other
        short, long_ = sorted((given(a), given(b)), key=len)
        return all(any(x.startswith(y) or y.startswith(x) for x in long_) for y in short)

    if not given(name):
        return name                    # a bare surname says nothing about which person of that name
    same = {p for p in persons if surname(p) == surname(name) and given(p) and fits(p, name)}
    return same.pop() if len(same) == 1 else name


def pick_name(a: str, b: str, diary_text: str = "") -> str:
    """One spelling for the person both judges name: the one the diary writes most often (a judge
    may add first names from its own knowledge, "Christian Daniel Erdt" for the diary's "Erdt", or
    follow a misreading, "Herbert Bezzel" for "Einhard Bezzel"), else the one with fewer words."""
    if a == b:
        return a
    words = lambda n: len(re.findall(r"[A-Za-zÄÖÜäöüß]+", re.sub(r"\b(?:Dr|Herr|Hr|Prof|Freund)\.?\s", "", n)))   # noqa: E731
    return max((a, b), key=lambda n: (words(n) > 1, diary_text.count(n), -words(n), -len(n)))   # a bare surname only when both are


def cmd_merge(a) -> None:
    root = Path(a.out)
    diary_text = "\n".join(r.get("text_clean", "") for r in read_csv(Path(a.corpus) / "entries.csv")) if a.corpus else ""
    cands = {r["entry_id"]: r for r in read_csv(root / "candidates.csv")}
    gem = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (root / "gemini").glob("*.json")}
    cla = {}
    for p in (root / "claude" / "answers").glob("*.json"):
        try:
            cla[p.stem] = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            print("unreadable", p)
    dossier_records = {}
    for p in (root / "claude" / "dossiers").glob("*.json"):
        blk = json.loads(p.read_text(encoding="utf-8"))["block"]
        part = blk.split("### Records credited to Laubmann", 1)[-1]
        dossier_records[p.stem] = [json.loads(line) for line in part.strip().splitlines() if line.startswith("{")]
    with_of = {(eid, r["i"]): r.get("with") or [] for eid, recs in dossier_records.items() for r in recs}
    authors_of, kind_of, persons_of = {}, {}, {}
    for p in (root / "claude" / "dossiers").glob("*.json"):
        blk = json.loads(p.read_text(encoding="utf-8"))["block"]
        sec = dict(re.findall(r"### ([^\n]+)\n(.*?)(?=\n### |\Z)", blk, re.S))
        persons_of[p.stem] = [re.sub(r"\s*\([^)]*\)$", "", x).strip()
                              for x in sec.get("Persons the graph found in the entry", "").strip().split("; ") if x.strip()]
        k = re.search(r"kind in the graph: ([a-z-]+)", blk)
        kind_of[p.stem] = k.group(1) if k else ""
        authors_of[p.stem] = text_authors(sec.get("End of the previous entry", ""), sec.get("Text of this entry", ""))
    rows, judgements = [], []
    stats = collections.Counter()
    for eid, g in gem.items():
        indices = g.get("records") or []
        gv = verdicts(g.get("answer"), indices)
        has_claude = eid in cla
        cv = verdicts(cla[eid], indices) if has_claude else {}
        written = {r["i"]: r.get("name", "") for r in dossier_records.get(eid, [])}
        observers = {}
        for i in indices:
            a1, a2 = gv.get(i), cv.get(i)
            stats["records"] += 1
            if a1 is None:
                stats["gemini missing"] += 1
            gem_other = a1 is not None and a1[0] == "other"
            if gem_other:
                stats["gemini other"] += 1
            if not has_claude:
                if gem_other:
                    stats["gemini other, no second judge"] += 1
                continue
            cl_other = a2 is not None and a2[0] == "other"
            if cl_other:
                stats["claude other"] += 1
            decision, by, typ, conf = "keep", None, None, None
            if gem_other and cl_other:
                s1, s2 = surname(a1[1]), surname(a2[1])
                typ = a1[2] if a1[2] == a2[2] else "third-party-report"
                conf = round(1 - (1 - a1[3]) * (1 - a2[3]), 3)    # two agreeing checks as independent evidence (record_check_combine.py)
                if s1 and s1 == s2:
                    decision, by = "apply", entry_spelling(pick_name(a1[1], a2[1], diary_text), persons_of.get(eid, []))
                    stats["agree: other, same person"] += 1
                elif not s1 and not s2:
                    decision = "apply"
                    stats["agree: other, author unknown"] += 1
                elif not s1 or not s2:
                    # both: not Laubmann's; only one names the author -> the name only where the diary's
                    # own cover note, signature or report series names the same person, else unknown
                    named = a1[1] or a2[1]
                    if surname(named) in authors_of.get(eid, set()):
                        decision, by = "apply", entry_spelling(named, persons_of.get(eid, []))
                        stats["agree: other, one names the author, the text confirms"] += 1
                    else:
                        decision, by = "apply", None
                        stats["agree: other, one names the author, unknown"] += 1
                else:
                    decision, by = "apply", None       # both: not Laubmann's, but different authors -> unknown
                    stats["agree: other, different authors, unknown"] += 1
            elif gem_other or cl_other:
                decision = "disagree"
                stats["disagree: other vs diarist"] += 1
            else:
                stats["agree: diarist"] += 1
            judgements.append({"entry_id": eid, "entry_uid": g["entry_uid"], "obs_index": i, "written": written.get(i, ""),
                               "gemini": "|".join(str(x) for x in (a1 or ("—",))[:3]), "claude": "|".join(str(x) for x in (a2 or ("—",))[:3]),
                               "decision": decision, "observer": by or "", "record_type": typ or "", "confidence": conf if conf is not None else "",
                               "why": (a1[4] if gem_other else "") or (a2[4] if cl_other else "")})
            if decision == "apply":
                observers[i] = (by, typ, conf, judgements[-1]["why"],
                                "gemini+claude+text" if by and not (s1 and s1 == s2) else "gemini+claude")
        for i, (by, typ, conf, why, sources) in observers.items():
            base = {"entry_uid": g["entry_uid"], "entry_id": eid, "written": written.get(i, ""), "obs_index": i, "action": "set",
                    "reason": "Zuschreibung: " + (f"{by}" if by else "nicht Laubmann, Verfasser unbekannt") + (f" ({why})" if why else ""),
                    "reviewed_by": "machine:gemini-3.8-flash+claude-sonnet-5-5", "reviewed_at": a.date, "confidence": conf,
                    "agreement": 2, "sources": sources}
            rows.append(dict(base, field="record_type", new_value=typ, old_value="field-observation"))
            if by:
                rows.append(dict(base, field="observer", new_value=by, old_value=DIARIST))
                with_ = with_of.get((eid, i)) or []
                kept = [p for p in with_ if surname(p) != surname(by)]
                if len(kept) < len(with_):          # the author was listed as Laubmann's companion
                    rows.append(dict(base, field="co_observers", new_value="; ".join(kept) or "-", old_value="; ".join(with_)))
        report = {(cla.get(eid) or {}).get("report"), (g.get("answer") or {}).get("report")}
        if report == {"all"} and observers and len(observers) == len(indices):
            stats["entries: both say the whole entry is a report"] += 1
            kind = kind_of.get(eid, "")
            if kind not in ("correspondence", "species-digest", "retrospective"):
                rows.append({"entry_uid": g["entry_uid"], "entry_id": eid, "written": "", "action": "set", "field": "entry_kind",
                             "new_value": "correspondence", "old_value": kind,
                             "reason": "Eintrag ist ganz ein Bericht oder Brief eines anderen (beide Prüfungen)",
                             "reviewed_by": "machine:gemini-3.8-flash+claude-sonnet-5-5", "reviewed_at": a.date,
                             "confidence": min(v[2] for v in observers.values()), "agreement": 2, "sources": "gemini+claude"})
                stats["entries: kind set to correspondence"] += 1
    fields = ["entry_uid", "entry_id", "written", "obs_index", "occurrence", "action", "field", "new_value", "old_value",
              "reason", "reviewed_by", "reviewed_at", "confidence", "agreement", "sources"]
    out_csv = Path(a.csv) if a.csv else root / "attribution_machine.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    with open(root / "attribution_judgements.csv", "w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=list(judgements[0]) if judgements else ["entry_id"])
        w.writeheader()
        w.writerows(judgements)
    by_person = collections.Counter(r["new_value"] for r in rows if r["field"] == "observer")
    summary = {"candidates": len(cands), "gemini answers": len(gem), "claude answers": len(cla), **stats,
               "correction rows": len(rows), "records re-attributed": sum(1 for r in rows if r["field"] == "record_type"),
               "entries": len({r["entry_uid"] for r in rows}), "observers": dict(by_person.most_common(30))}
    (root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("candidates", "run", "dossiers"):
        p = sub.add_parser(name)
        p.add_argument("triples")
        p.add_argument("--export", required=True)
        p.add_argument("--corpus", default=str(REPO / "data" / "corpus_patched"))
        p.add_argument("--out", required=True)
        p.add_argument("--pages", default=str(REPO / "data" / "pages_jpg"))
        p.add_argument("--only", default=None)
    sub.choices["run"].add_argument("--model", default="gemini-3.8-flash")
    sub.choices["run"].add_argument("--cache", default=str(REPO / "data" / "cache" / "attribution_check_v1"))
    sub.choices["run"].add_argument("--budget", type=float, default=10.0)
    sub.choices["run"].add_argument("--concurrency", type=int, default=16)
    sub.choices["run"].add_argument("--limit", type=int, default=0)
    sub.choices["dossiers"].add_argument("--batch-records", type=int, default=120)
    sub.choices["dossiers"].add_argument("--batch-entries", type=int, default=8)
    p = sub.add_parser("pages")
    p.add_argument("--out", required=True)
    p.add_argument("--pages", default=str(REPO / "data" / "pages_jpg"))
    p.add_argument("--drive-pages", required=True)
    p = sub.add_parser("merge")
    p.add_argument("--out", required=True)
    p.add_argument("--corpus", default=str(REPO / "data" / "corpus_patched"), help="entries.csv: how often the diary writes a name")
    p.add_argument("--csv", default=None)
    p.add_argument("--date", default="2026-10-05")
    a = ap.parse_args()
    {"candidates": cmd_candidates, "pages": cmd_pages, "run": cmd_run, "dossiers": cmd_dossiers, "merge": cmd_merge}[a.cmd](a)


if __name__ == "__main__":
    main()
