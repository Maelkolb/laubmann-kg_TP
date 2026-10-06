"""Review layer of the graph validation page: what was changed automatically, what the checks found.

The graph explorer shows what the published graph says. This script collects,
per entry and per name, everything a reviewer needs next to it:

* where the entry stands on its page scans (region boxes) and where each record's line is,
* the corrections the visual reading made to the transcription (old -> new, applied or not,
  kind of change, the verdicts of the machine checks),
* what the pipeline excluded or changed on its own (QA flags, value corrections),
* the record checks: Gemini on every entry (record_check.py), Claude subagents on the
  sample dossiers (merge.py graph_checks*.csv) — verdict, wrong fields, proposed values,
  missing records, entry date/place/kind,
* the name-level decisions of the machine review (identities_machine.csv: applied above
  the thresholds, suggestions below) with the link before and after,
* the text inserts of the entry and whether their text was read by the extraction.

    python tools/validation_ui/graph_check/build_review.py --payload payload.b64 --payload-before payload_pipeline.b64 \\
        --triples triples.pkl --corpus data/corpus_patched --geometry pages_geometry.json \\
        --review <export>/review --dwca <export>/dwca --machine data/review/machine --drive-regions drive_regions.json \\
        --record-check <workdir>/record_check --sonnet-check <machine_review dir> --out review.json

Output (JSON; coordinates are fractions of the page width/height, 0-1):

    meta      export, built, thresholds, counts
    pages     [[page_id, width, height], ...]            index = page index used below
    entries   {entry_id: {
        uid    corpus entry uid ("e_…")
        reg    [[page, x0, y0, x1, y1, approx], ...]     the entry's text on its pages; approx 1 = the entry shares the
                                                         layout region with a neighbour, box estimated from its lines
        tc     [[old, new, applied, pos, kind, rel, sonnet, gemini, better], ...]   reading corrections;
               pos = offset of `new` in the entry text (dwc:fieldNotes) or -1; kind markup | punctuation | case |
               number | word | insertion | deletion; rel = letters b (a bird name of the graph changed), n (a
               number changed), p (a place name changed); sonnet/gemini = right | partly | wrong | unclear | ""
               (gemini "" on a checked entry = no objection); better = the checker's own reading
        qa     [[reason, action, value, detail], ...]    QA flags of the entry (action excluded | flagged)
        rec    {obs_index: {w written name, occ occurrence among the entry's records of that name,
                            loc [page, x0, y0, x1, y1, approx, fx0, fx1] | absent  (line of the name; fx = word span
                            as fractions of the line), g {v, f, fix, c, q, qin, why} Gemini check, s {...} Claude check,
                            auto [[layer, from, to, why], ...] changes applied to this record without a human}}
               v = ok | wrong | spurious | unsure; f = wrong fields; fix = proposed values; c = confidence;
               q = quoted words of the page; qin 1 = the quote stands in the transcription
               t = corpus tier of the record (with --dwca), tw = the reasons that keep it out of the next tier,
                 codes and rules in corpus_tiers.py (RULES), calibration in docs/corpus_tiers.md:
                 0 outside the core   the occurrence is in doubt: spurious | flagged (species, count, date, status) |
                                      unchecked | duplicate | no-taxon | list | literature-date | entry-checks |
                                      ungrounded | long-entry
                 1 core               another field is in doubt: flagged-attribution | flagged-place | flagged-georef |
                                      attribution | identification | count | absence | reading | entry | entry-place
                 2 strict core        no-coords | georef-unconfirmed | place-doubt
                 3 strict core with coordinates
               q = estimated quality (with --quality; then t and tw are left out), record_quality.py:
                 p estimated probability that a field is wrong, po the same for the occurrence (exists, species, count,
                 date), pc for the coordinates (absent without coordinates), lv level 1 (< 10 %) 2 (< 25 %) 3 (< 50 %) 4,
                 s status per field in the order exists, species, count, date, place, observer, record type (ok | one |
                 c1 | c2 | both | na), then coordinates (rev | gaz | rev-c1 | gaz-c1 | none); pf probability per field in the
                 same order (without coordinates); x {ex|sp|n|d|pl|ob|ty: the blind check's reading where it differs}
        gone   [[reason, value, detail], ...]            what QA or a review decision removed from the entry (QA flags
                                                         with action excluded: non_bird, review_not_taxon, value_dropped …)
        miss   [{src g|s, kind, text, de, sci, count, loc, date, obs, c, note, in_text}, ...]   what the text states and the
               graph lacks; kind observation | person | travel | weather | other; in_text 1 = the passage stands in the entry text
        ent    {g: {date_ok, date, place_ok, place, kind_ok, kind}, s: {..., note}}   entry-level findings (only when not
               ok, and only proposals that differ from the graph; kind within the vocabulary of entry kinds)
        ins    [[region_uid, kind, characters, state], ...]   text inserts: state read | partly | unread | read-in:<entry_id>
        media  [[region_uid, kind, page, x0, y0, x1, y1], ...]   every multimodal region of the entry (drawing, map,
               photograph, print, object, text-insert, list; graph node data:region_<region_uid>); the box on the page
               scan is absent when the layout geometry does not know the region
        chk    "g", "s" or "gs": which record checks saw the entry
    }}
    names     {"<section>|<name lower-case>": {rows: [{n (name as written), d, t, auth, sci, rank, lat, lon, unc, eunis, c, ag, src, rnd, why, auto}],
               before: [...], now: [...]}}   section taxa | persons | places | habitats; rows = machine review rows
               (auto 1 = applied in the graph); before/now = the entity link without / with the machine review
               (taxa [label, scientific name, GBIF key]; persons [label, Wikidata, GND]; places [label, lat, lon,
               GeoNames, Wikidata, source]; habitats [label, EUNIS code, match]); before only where an applied
               row changed the link
    crops     {region_uid: Google Drive file id of the crop image}   (tools/validation_ui/drive_ids.py --regions), for
              the multimodal regions and for the body-text regions; local copies of the multimodal crops:
              <region_uid>.jpg (tools/export_region_crops.py)
    regions   {region_uid: [page, x0, y0, x1, y1]}   every body-text region of the graph (lkg:SourceRegion node
              data:region_<region_uid>): its page and box on the page scan (box absent when unknown)
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "machine_review"))
from common import load_payload  # noqa: E402
from prepare_entries import GraphView, graph_records  # noqa: E402
import corpus_tiers  # noqa: E402
from laubmann_kg.extraction.reading import _locate  # noqa: E402
from laubmann_kg.review.better_readings import (LAYER_FIELDS, classify, commentary, doubled_edges, doubled_in_reading,  # noqa: E402
                                                 fold, machine_decision, name_indexes, overrun_in_reading, place)

csv.field_size_limit(10 ** 9)
TAG = re.compile(r"</?[a-zA-Z][^>]*>")
PUNCT = re.compile(r"[\s\.,;:!\?\-–—\(\)\[\]\"'„“”‚‘’/]+")
WORD = re.compile(r"[A-Za-zÄÖÜäöüß]{4,}")
ENTRY_KINDS = ("field-day", "species-digest", "retrospective", "correspondence", "other")   # normalization.vocabularies


def read_csv(path, delimiter=","):
    p = Path(path) if path else None
    if not p or not p.exists():
        return []
    with open(p, encoding="utf-8-sig", newline="") as h:
        return list(csv.DictReader(h, delimiter=delimiter))


def plain(s: str) -> str:
    return re.sub(r"\s+", " ", TAG.sub("", s or "")).strip().casefold()


def change_kind(old: str, new: str) -> str:
    o, n = TAG.sub("", old), TAG.sub("", new)
    if o == n:
        return "markup"
    if PUNCT.sub("", o) == PUNCT.sub("", n):
        return "punctuation"
    if PUNCT.sub("", o).casefold() == PUNCT.sub("", n).casefold():
        return "case"
    if re.findall(r"\d+", o) != re.findall(r"\d+", n):
        return "number"
    if len(n) - len(o) > 25:
        return "insertion"
    if len(o) - len(n) > 25:
        return "deletion"
    return "word"


def changed_words(old: str, new: str) -> set[str]:
    a = {w.casefold() for w in WORD.findall(TAG.sub("", old))}
    b = {w.casefold() for w in WORD.findall(TAG.sub("", new))}
    return a ^ b


def stem_in(words: set[str], names: set[str]) -> bool:
    return any((w[:len(w) - cut] if cut else w) in names for w in words for cut in (0, 1, 2))


def fnum(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--payload", required=True, help="payload of the graph the page shows (build_payload.py)")
    ap.add_argument("--payload-before", default=None, help="payload of the same run without the machine review")
    ap.add_argument("--triples", required=True)
    ap.add_argument("--corpus", required=True, help="corpus dir (corpus.json, entries.jsonl, multimodal_regions.jsonl)")
    ap.add_argument("--geometry", required=True, help="pages_geometry.json (page_geometry.py + line_profiles.py)")
    ap.add_argument("--review", required=True, help="the export's review/")
    ap.add_argument("--machine", default=None, help="data/review/machine (identities_machine.csv)")
    ap.add_argument("--record-check", default=None, help="record_check.py output folder (record_checks*.csv)")
    ap.add_argument("--sonnet-check", default=None, help="merge.py output folder (graph_checks*.csv, transcript_checks.csv)")
    ap.add_argument("--sonnet-stale", default=None, help="file with entry ids or uids whose records changed after the Sonnet "
                                                          "check: its record and missing-record findings are left out there")
    ap.add_argument("--drive-regions", default=None, help="drive_ids.py --regions: crop path -> Drive file id")
    ap.add_argument("--dwca", default=None, help="the export's dwca/ (occurrence.txt, event.txt): needed for the corpus tiers")
    ap.add_argument("--tiers-csv", default=None, help="also write the corpus tier of every occurrence (record_tiers.csv)")
    ap.add_argument("--region-decisions", default=None, help="region_quality_machine.csv: regions the graph no longer has are left "
                                                              "out, a region cut anew shows the new box (cut out of the page scan)")
    ap.add_argument("--quality", default=None, help="record_quality.py output folder (record_quality.csv, quality_summary.json): "
                                                     "every record gets its estimated quality q, the corpus tiers t / tw are left out")
    ap.add_argument("--text-layer", default=None,
                    help="the machine layer of the text this export applied (data/review/machine/text_layer_machine.csv): the "
                         "reading corrections are then taken from --reading-base under their original keys, each with what the graph "
                         "holds at its place")
    ap.add_argument("--reading-base", default=None,
                    help="the reading stage's corrections the text layer refers to (data/review/machine/reading_corrections_base.csv)")
    ap.add_argument("--transcript-checks", default=None,
                    help="the checks' verdicts on the reading corrections, when they come from another check run than --record-check "
                         "(their keys are the original corrections)")
    ap.add_argument("--machine-text-layer", default=None,
                    help="also write the machine layer of the text into this folder (data/review/machine): the checks' better "
                         "readings and the scan agent's corrections, each with how it reaches the graph (text_layer_machine.csv), "
                         "and the species and places the patched changes correct (value_corrections_text_machine.csv)")
    ap.add_argument("--min-confidence", type=float, default=0.9)
    ap.add_argument("--min-agreement", type=int, default=2)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    P = load_payload(args.payload)
    E, PG = P["E"], P["PG"]
    corpus = Path(args.corpus)
    geo = json.loads(Path(args.geometry).read_text(encoding="utf-8"))
    print("loading triples …", flush=True)
    G = GraphView(args.triples)

    # ------------------------------------------------------------ pages and entry regions
    pages, page_no = [], {}

    def page(pid: str) -> int:
        if pid not in page_no:
            g = geo.get(pid, {})
            page_no[pid] = len(pages)
            pages.append([pid, g.get("w", 0), g.get("h", 0)])
        return page_no[pid]

    stream = collections.defaultdict(list)       # volume -> [(start, end, page_id, region id, text)]
    pos = collections.defaultdict(int)
    corpus_pages = json.loads((corpus / "corpus.json").read_text(encoding="utf-8"))
    for pg in corpus_pages:
        vol = int(pg["volume"])
        for r in sorted(pg["regions"], key=lambda r: int(r.get("reading_order") or 0)):
            if r.get("type") not in ("ParagraphRegion", "ListRegion"):
                continue
            text = r.get("text") or ""
            stream[vol].append((pos[vol], pos[vol] + len(text), pg["page_id"], r["id"], text))
            pos[vol] += len(text) + 2
    spans = {}
    with open(corpus / "entries.jsonl", encoding="utf-8") as h:
        for line in h:
            d = json.loads(line)
            try:
                a, b = int(d["stream_start"]), int(d["stream_end"])
            except (KeyError, TypeError, ValueError):
                continue
            spans[d["entry_uid"]] = [(pid, rid, max(a, s) - s, min(b, e) - s, text)
                                     for s, e, pid, rid, text in stream[int(d["volume"])] if s < b and e > a]

    def frac(pid, box):
        g = geo.get(pid, {})
        w, hgt = g.get("w") or 0, g.get("h") or 0
        if not w or not hgt:
            return None
        x0, y0, x1, y1 = box
        return [round(x0 / w, 4), round(y0 / hgt, 4), round(x1 / w, 4), round(y1 / hgt, 4)]

    def entry_regions(uid):
        out = []
        for pid, rid, a, b, text in spans.get(uid, []):
            g = geo.get(pid, {})
            box = g.get("r", {}).get(rid)
            if not box:
                continue
            x0, y0, x1, y1 = box
            approx = 0
            if a > 0 or b < len(text):                       # the entry holds only some lines of the region
                lines = text.split("\n")
                n = len(lines)
                first = text.count("\n", 0, a)
                last = text.count("\n", 0, max(a, b - 1))
                bands = g.get("l", {}).get(rid)
                if bands and abs(len(bands) - n) <= max(1, 0.25 * n):
                    m = len(bands)
                    y0, y1 = bands[min(m - 1, int(first * m / n))][0], bands[min(m - 1, int(last * m / n))][1]
                else:
                    lh = (y1 - y0) / max(1, n)
                    y0, y1 = y0 + first * lh, y0 + (last + 1) * lh
                approx = 1
            f = frac(pid, (x0, y0, x1, y1))
            if f:
                out.append([page(pid)] + f + [approx])
        return out

    # ------------------------------------------------------------ names of the graph (to judge what a correction touches)
    taxon_names = {f[0].casefold() for f in P["taxon"]["forms"]} | {e[0].casefold() for e in P["taxon"]["ent"]}
    # single-word place names used at least three times (rare micro-toponyms are mostly common nouns)
    place_names = {f[0].casefold() for f in P["place"]["forms"] if " " not in f[0] and len(f[0]) >= 5 and f[1] >= 3}

    # ------------------------------------------------------------ inputs per entry
    review = Path(args.review)
    corr = collections.defaultdict(list)
    if args.text_layer and not args.reading_base:
        sys.exit("--text-layer needs --reading-base (the reading corrections the layer refers to)")
    for r in read_csv(Path(args.reading_base) if args.reading_base else review / "transcript_corrections.csv"):
        corr[r["entry_uid"]].append(r)
    layer_check, layer_scan = {}, collections.defaultdict(list)   # the text layer this export applied
    for r in read_csv(Path(args.text_layer)) if args.text_layer else []:
        if r["source"] == "check":
            layer_check[(r["entry_uid"], r["old_text"], r["new_text"])] = r
        else:
            layer_scan[r["entry_uid"]].append(r)
    scan_text = collections.defaultdict(list)   # the scan agent's corrections of the corrected text (machine layer, applied after the reading)
    for r in read_csv(Path(args.machine) / "text_corrections_machine.csv") if args.machine else []:
        if r.get("old_text") and r.get("new_text") and r["old_text"] != r["new_text"]:
            scan_text[r["entry_uid"]].append(r)
    layer_rows, value_rows = [], []
    if args.machine_text_layer and any("Maschinenprüfung" in (r.get("detail") or r.get("message") or "")
                                       for r in read_csv(review / "qa_flags.csv") if r.get("reason") == "reading_corrected"):
        sys.exit("--machine-text-layer needs the export WITHOUT the text layer (its changes are computed on the reading stage's "
                 "text); this export already applied one")
    taxa_idx, places_idx = name_indexes(P)
    places_used = collections.defaultdict(set)   # every place form an entry uses: header, records, travel legs
    for men in P["place"]["men"]:
        places_used[P["E"][men[1]][0]].add(fold(P["place"]["forms"][men[0]][0]))
    qa = collections.defaultdict(list)
    for r in read_csv(review / "qa_flags.csv"):
        qa[r["entry_uid"]].append(r)

    def unmangle(v):   # "RabenkrÃ¤he": UTF-8 read as cp1252 by one of the agents
        if isinstance(v, str) and "Ã" in v:
            try:
                return v.encode("cp1252").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                return v
        return v

    def checks(folder, records, missing, entries, tchecks):
        d = Path(folder) if folder else None
        rec = collections.defaultdict(dict)
        for r in read_csv(d / records) if d else []:
            r = {k: unmangle(v) for k, v in r.items()}
            if r["obs_index"] not in ("", None):
                rec[r["entry_uid"]][int(r["obs_index"])] = r
        clean = lambda rows: [{k: unmangle(v) for k, v in r.items()} for r in rows]
        mis = collections.defaultdict(list)
        for r in clean(read_csv(d / missing)) if d else []:
            mis[r["entry_uid"]].append(r)
        ent = {r["entry_uid"]: r for r in (clean(read_csv(d / entries)) if d else [])}
        tpath = Path(tchecks) if Path(tchecks).is_absolute() or Path(tchecks).exists() else (d / tchecks if d else None)
        tc = {(r["entry_uid"], r["old_text"], r["new_text"]): r for r in (clean(read_csv(tpath)) if tpath else [])}
        return rec, mis, ent, tc

    g_rec, g_mis, g_ent, g_tc = checks(args.record_check, "record_checks.csv", "record_checks_missing.csv",
                                       "record_checks_entries.csv", args.transcript_checks or "transcript_checks_gemini.csv")
    s_rec, s_mis, s_ent, s_tc = checks(args.sonnet_check, "graph_checks.csv", "graph_checks_missing.csv",
                                       "graph_checks_entries.csv", "transcript_checks.csv")
    s_stale = set(Path(args.sonnet_stale).read_text(encoding="utf-8").split()) if args.sonnet_stale else set()
    pre_reading = {}   # the transcription the reading stage corrects
    if args.machine_text_layer:
        with open(corpus / "entries.csv", encoding="utf-8-sig", newline="") as h:
            pre_reading = {r["entry_uid"]: r["text_clean"] for r in csv.DictReader(h)}

    def finding(r, src):
        if not r or r.get("verdict") in ("", "unchecked", None):
            return None
        out = {"v": r["verdict"]}
        if r["verdict"] != "ok":
            fix = json.loads(r["correction"]) if r.get("correction") else {}
            out.update({"f": [x for x in re.split(r"[;,]\s*", r.get("fields") or "") if x], "fix": fix, "c": fnum(r.get("confidence")),
                        "why": r.get("reason") or ""})
            if src == "g":
                out.update({"q": r.get("quote") or "", "qin": 1 if r.get("quote_in_text") == "y" else 0})
        return out

    def truthy(v):
        return {"True": True, "False": False, "true": True, "false": False}.get(str(v), None)

    def entry_finding(r, src, current):
        """Entry-level objections; a proposal equal to the graph's value or (kind) outside the
        vocabulary of entry kinds is not one."""
        if not r:
            return None
        out = {}
        for k in ("date", "place", "kind"):
            if truthy(r.get(f"{k}_ok")) is False:
                value = (r.get(k) or "").strip()
                if value and (value.casefold() == (current[k] or "").casefold() or (k == "kind" and value not in ENTRY_KINDS)):
                    continue
                out[f"{k}_ok"] = False
                if value:
                    out[k] = value
        if src == "s" and out and r.get("summary"):
            out["note"] = r["summary"]
        return out or None

    # taxon mentions of an entry in extraction order (build_payload.py) carry the line location
    men_by_entry = collections.defaultdict(list)
    for m in P["taxon"]["men"]:
        men_by_entry[m[1]].append(m)

    # ------------------------------------------------------------ text inserts
    inserts = collections.defaultdict(list)
    insert_texts = collections.defaultdict(list)
    media = collections.defaultdict(list)
    crops: dict = {}
    drive_regions = json.loads(Path(args.drive_regions).read_text(encoding="utf-8")) if args.drive_regions else {}
    mm_path = corpus / "multimodal_regions.jsonl"
    new_box: dict = {}
    if mm_path.exists():
        ids = {e[1]: e[0] for e in E}
        orig = {}
        with open(corpus / "entries.csv", encoding="utf-8-sig", newline="") as h:
            for r in csv.DictReader(h):
                orig[r["entry_uid"]] = r["text_clean"]

        def words(s):
            return re.sub(r"\W+", " ", TAG.sub("", s or "")).casefold().split()

        index = collections.defaultdict(set)
        for uid, text in orig.items():
            w = words(text)
            for i in range(len(w) - 4):
                index[" ".join(w[i:i + 5])].add(uid)
        mm_in_graph = {str(n).rsplit("region_", 1)[-1] for n, ts in G.typ.items() if "MultimodalRegion" in ts}
        if args.region_decisions:
            for d in csv.DictReader(open(args.region_decisions, encoding="utf-8", newline="")):
                if d.get("crop") and d.get("box"):
                    x0, y0, x1, y1 = json.loads(d["box"])
                    new_box[d["region_uid"]] = [max(0.0, x0 - 0.01), max(0.0, y0 - 0.01), min(1.0, x1 + 0.01), min(1.0, y1 + 0.01)]
        for line in mm_path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line) if line.strip() else None
            uid = (r or {}).get("entry_uid") or ""
            if not r or uid not in ids or (mm_in_graph and r["region_uid"] not in mm_in_graph):
                continue
            # every region of the entry with its crop: box on the page scan (the layout region the crop
            # was cut from, rNN in the crop's file name) and the Drive id of the crop image; a region the
            # region check cut anew shows its new box, cut out of the page scan
            m = re.search(r"/(r\d+)_", r.get("crop") or "")
            box = geo.get(r["page_id"], {}).get("r", {}).get(m.group(1)) if m else None
            f = frac(r["page_id"], box) if box else None
            if r["region_uid"] in new_box:
                f = [round(x, 4) for x in new_box[r["region_uid"]]]
            media[uid].append([r["region_uid"], r["kind"], page(r["page_id"])] + (f or []))
            if drive_regions.get(r.get("crop") or "") and r["region_uid"] not in new_box:
                crops[r["region_uid"]] = drive_regions[r["crop"]]
            if r.get("kind") not in ("text-insert", "list") or not (r.get("visible_text") or "").strip():
                continue
            insert_texts[uid].append(r["visible_text"])
            w = words(r["visible_text"])
            grams = [" ".join(w[i:i + 5]) for i in range(0, max(1, len(w) - 4), 5)]
            where = collections.Counter(u for g in grams for u in index.get(g, ()))
            own = where.get(uid, 0) / max(1, len(grams))
            best = where.most_common(1)
            if own >= 0.6:
                state = "read"
            elif best and best[0][0] != uid and best[0][1] / max(1, len(grams)) >= 0.6 and best[0][0] in ids:
                state = "read-in:" + ids[best[0][0]]
            else:
                state = "partly" if own >= 0.2 else "unread"
            inserts[uid].append([r["region_uid"], r["kind"], len(r["visible_text"]), state])

    # ------------------------------------------------------------ body-text regions of the graph
    # (lkg:SourceRegion nodes data:region_<uid>): box on the page scan and Drive id of the region's crop
    regions: dict = {}
    in_graph = {str(n).rsplit("region_", 1)[-1] for n, ts in G.typ.items() if "SourceRegion" in ts}
    for pg in corpus_pages:
        for r in pg["regions"]:
            uid = r.get("region_uid")
            if uid not in in_graph or uid in crops or uid in new_box:
                continue
            box = geo.get(pg["page_id"], {}).get("r", {}).get(r["id"])
            f = frac(pg["page_id"], box) if box else None
            regions[uid] = [page(pg["page_id"])] + (f or [])
            if drive_regions.get(r.get("crop") or ""):
                crops[uid] = drive_regions[r["crop"]]

    # ------------------------------------------------------------ what the corpus tiers need
    occ_rows, duplicates = {}, set()
    if args.dwca:
        seen = set()
        with open(Path(args.dwca) / "occurrence.txt", encoding="utf-8", newline="") as h:
            rd = csv.reader(h, delimiter="\t", quoting=csv.QUOTE_NONE)
            head = next(rd)
            for row in rd:
                d = dict(zip(head, row))
                occ_rows[d["occurrenceID"]] = d
                key = tuple(d[k] for k in ("eventID", "scientificName", "vernacularName", "individualCount", "locality", "eventDate",
                                           "sex", "lifeStage", "behavior"))
                if key in seen:
                    duplicates.add(d["occurrenceID"])          # as tools/validate_export.py: same event, taxon, count, place, date …
                seen.add(key)
    events, place_uses = {}, collections.Counter()
    if args.dwca:
        with open(Path(args.dwca) / "event.txt", encoding="utf-8", newline="") as h:
            rd = csv.reader(h, delimiter="\t", quoting=csv.QUOTE_NONE)
            head = next(rd)
            for row in rd:
                d = dict(zip(head, row))
                events[d["eventID"]] = d
                place_uses[d["locality"]] += 1
    tiers = corpus_tiers.Tiers(place_uses)
    data_ns = next(iter(occ_rows), "obs_").rsplit("obs_", 1)[0]
    form_class = {}
    for f in P["taxon"]["forms"]:
        form_class.setdefault(f[0].casefold(), f[3])           # A = an attested German name of the linked taxon (build_payload.py)
    applied_taxa = {}
    for r in read_csv(Path(args.machine) / "identities_machine.csv") if args.machine else []:
        if r["section"] == "taxa" and (fnum(r.get("confidence")) or 0) >= args.min_confidence \
                and int(float(r.get("agreement") or 0)) >= args.min_agreement:
            applied_taxa[r["name_form"].casefold()] = r["decision"]

    # ------------------------------------------------------------ entries
    entries = {}
    tier_ids = {}
    counts = collections.Counter()
    for ei, e in enumerate(E):
        uid = e[1]
        s = G.entries.get(e[0])
        graph = graph_records(G, s, uid, e[2], {}) if s is not None else {"observations": []}
        text = e[7] or ""
        low = text
        rec = {}
        men = men_by_entry.get(ei, [])
        obs = graph["observations"]
        occ = collections.Counter()
        aligned = len(men) == len(obs)
        def match_checks(table, src):   # a check belongs to the record with its written name (and occurrence), else to its index if the species agree
            by_name = collections.defaultdict(list)
            for o in obs:
                by_name[fold(o["written"])].append(o)
            at_index = {o["index"]: o for o in obs}
            out = {}
            for idx, r in sorted(table.items()):
                named = by_name.get(fold(r.get("written")), [])
                occ = int(r.get("occurrence") or 0) if str(r.get("occurrence") or "0").isdigit() else 0
                o = named[occ] if occ < len(named) else (named[0] if len(named) == 1 else None)
                if o is None:
                    o = at_index.get(idx)
                    if o is None or fold(o.get("taxon")) != fold(r.get("taxon")):
                        counts[f"record checks ({src}) dropped: no record with that name or species"] += 1
                        continue
                    counts[f"record checks ({src}) matched by index and species"] += 1
                elif o["index"] != idx:
                    counts[f"record checks ({src}) moved to the record of that name"] += 1
                if o["index"] in out:
                    counts[f"record checks ({src}) dropped: two checks for one record"] += 1
                    continue
                out[o["index"]] = r
            return out

        stale = uid in s_stale or e[0] in s_stale
        if stale and (s_rec.get(uid) or s_mis.get(uid)):
            counts["record checks (s) left out: the entry's records changed after the check"] += len(s_rec.get(uid, {})) + len(s_mis.get(uid, []))
        g_map, s_map = match_checks(g_rec.get(uid, {}), "g"), match_checks({} if stale else s_rec.get(uid, {}), "s")
        for k, o in enumerate(obs):
            name = o["written"].casefold()
            item = {"w": o["written"], "occ": occ[name]}
            occ[name] += 1
            loc = men[k][4] if aligned else None
            if isinstance(loc, list) and len(loc) >= 8:
                pid = PG[loc[0]][0]
                f = frac(pid, loc[1:5])
                if f:
                    item["loc"] = [page(pid)] + f + [loc[5], loc[6], loc[7]]
            for src, mapped in (("g", g_map), ("s", s_map)):
                fd = finding(mapped.get(o["index"]), src)
                if fd:
                    item[src] = fd
            rec[str(o["index"])] = item
            counts["records"] += 1
            counts["records located"] += "loc" in item
        # reading corrections: each with what the graph holds at its place (cur, its position) and whether the
        # machine layer changed it there (the checks' better reading, the scan agent's correction)
        tcs, at, changes = [], 0, []
        g_seen, s_seen = uid in g_ent, uid in s_ent

        def find_cur(cands, start):
            for cand in cands:
                for probe in (cand, TAG.sub("", cand)) if cand else ():
                    q = text.find(probe, start)
                    if q < 0:
                        q = text.find(probe)
                    if q >= 0:
                        return q, probe
            return -1, ""

        for c in corr.get(uid, []):
            old, new, applied = c["old_text"], c["new_text"], 1 if c.get("applied") == "y" else 0
            kind = change_kind(old, new)
            rel = ""
            if kind not in ("markup", "punctuation", "case"):
                cw = changed_words(old, new)
                rel = ("b" if stem_in(cw, taxon_names) else "") + ("n" if kind == "number" else "") + ("p" if stem_in(cw, place_names) else "")
            lr = layer_check.get((uid, old, new))
            stage = new if applied else old                 # what the reading stage left at this place
            p, cur = find_cur(([lr["final_text"]] if lr else []) + [stage], at if applied else 0)
            if applied and p >= 0:
                at = p
            machine_in = bool(lr) and cur in (lr["final_text"], TAG.sub("", lr["final_text"])) and lr["final_text"] != stage
            sv = (s_tc.get((uid, old, new)) or {}).get("verdict", "") if s_seen else ""
            gr = g_tc.get((uid, old, new)) or {}
            better = gr.get("better_text") or (s_tc.get((uid, old, new)) or {}).get("better_text") or ""
            # the checks' better reading on the correction's span ('' none, None not placeable; then the loosely cut
            # reading for the reviewer's form). With a text layer: the reading the layer put there.
            if lr:
                placed = lr["final_text"] if (machine_in or cur == stage == lr["final_text"]) else None
                loose = lr["final_text"] if placed is None else ""
            else:
                placed = place(old, new, bool(applied), p if cur == new else -1, better, text)
                loose = place(old, new, bool(applied), p if cur == new else -1, better, text, loose=True) if placed is None else ""
            tcs.append([old, new, applied, p, kind, rel, sv, gr.get("verdict", ""), better, placed, loose, "", cur, int(machine_in)])
            counts["corrections"] += 1
            counts["corrections record-relevant"] += bool(rel)
            counts["corrections changed in the graph by the text layer"] += machine_in
            if lr and not machine_in:
                counts["text layer changes not found in the graph"] += 1
            if args.text_layer:
                continue
            md = machine_decision(old, new, bool(applied), placed)
            if md and not (new if applied else old):   # an insertion without text to stand on: left to the reviewer
                md = None
            at_old = _locate(text, old) if md and not applied else None
            if md and not (at_old if not applied else (p >= 0 or _locate(text, new))):
                counts["better readings whose place is not in the graph text, left to the reviewer"] += 1
                md = None
            if md:
                changes.append({"entry_uid": uid, "entry_id": e[0], "source": "check", "old_text": old, "new_text": new, "decision": md[0],
                                "final_text": md[1], "text_now": new if applied else old,
                                "pos": p if applied else (at_old[0] if at_old and not at_old[2] else -1),
                                "header": (p == 0) if applied else text.startswith(old),
                                "note": "bessere Lesung der Prüfung", "reviewed_by": "machine:" + ("gemini" if gr.get("better_text") else "claude") + " (scan)"})
                counts["corrections, better reading applied by the machine layer"] += 1
            elif better and placed is None:
                counts["corrections, better reading not placeable"] += 1
        scan_rows = layer_scan.get(uid, []) if args.text_layer else []
        scan_layered = {(r["old_text"], r["new_text"]) for r in scan_rows}
        for r in scan_text.get(uid, []):   # the scan agent's corrections
            old, new = r["old_text"], r["new_text"]
            if any(t[0] == old and t[1] == new for t in tcs):
                continue
            kind = change_kind(old, new)
            cw = changed_words(old, new)
            rel = ("b" if stem_in(cw, taxon_names) else "") + ("n" if kind == "number" else "") + ("p" if stem_in(cw, place_names) else "")
            doubt = commentary(old, new)   # "vermutlich Bidingen", "(unsicher)": a note of the agent, not a reading
            in_layer = (old, new) in scan_layered
            pc, cur = find_cur(([new] if in_layer else []) + [old], 0)
            machine_in = in_layer and cur in (new, TAG.sub("", new))
            tcs.append([old, new, 0, pc, kind, rel, "", "", "", "" if doubt else new, "", "scan", cur, int(machine_in)])
            counts["scan agent text corrections"] += 1
            counts["corrections changed in the graph by the text layer"] += machine_in
            if in_layer and not machine_in:
                counts["text layer changes not found in the graph"] += 1
            if doubt:
                counts["scan agent text corrections with a doubt, left to the reviewer"] += 1
                continue
            if args.text_layer:
                continue
            at_old = _locate(text, old)
            if not at_old:   # made on an earlier version of the text: the words are not there any more
                counts["scan agent text corrections not in this text, left out"] += 1
                continue
            changes.append({"entry_uid": uid, "entry_id": e[0], "source": "scan", "old_text": old, "new_text": new, "decision": "accept",
                            "final_text": new, "text_now": old, "pos": at_old[0] if at_old and not at_old[2] else -1,
                            "header": text.startswith(old), "note": r.get("note") or "",
                            "reviewed_by": r.get("reviewed_by") or "machine:scan agent"})
        here = {fold(x) for o in obs for x in (o.get("locality"), o.get("place")) if x} | {fold(e[6]), fold(e[9] if len(e) > 9 else "")}
        here |= places_used.get(e[0], set())
        here.discard("")

        def judge(cs):
            return [classify(c["text_now"], c["final_text"], header=c["header"], records=obs, places_here=here, taxa=taxa_idx,
                             places=places_idx, entry_place=e[6] or "", location_raw=(e[9] if len(e) > 9 else "") or "") for c in cs]

        def leave_out(cs, twice, why="better readings that would double a word at their edge, left to the reviewer"):
            counts[why] += len(twice)   # cut one word too wide: the word stands twice in the text then
            return [c for i, c in enumerate(cs) if i not in twice]

        if changes and (twice := doubled_edges(text, changes)):   # in the graph text, where they are patched
            changes = leave_out(changes, twice)
        judged = judge(changes)
        if any(j[0] == "before" for j in judged) and uid in pre_reading and \
                (twice := doubled_in_reading(pre_reading[uid], [(t[0], t[1]) for t in tcs], changes)):   # in the reading stage
            changes = leave_out(changes, twice)
            judged = judge(changes)
        if any(j[0] == "before" for j in judged) and uid in pre_reading and \
                (hit := overrun_in_reading(pre_reading[uid], [(t[0], t[1]) for t in tcs], changes)):
            changes = leave_out(changes, hit, "better readings a later correction of the reading would land in, left to the reviewer")
            judged = judge(changes)
        if changes:   # how each change of the machine layer reaches the graph: patched after the extraction, or read anew
            mode = "before" if any(j[0] == "before" for j in judged) else "after"
            counts[f"text layer entries {mode}"] += 1
            placed_once = set()
            for c, (_, vals) in zip(changes, judged):
                spot = (c["source"], c["old_text"], c["new_text"], c["pos"])
                if spot in placed_once:   # the reading listed one correction twice: one change at one place
                    continue
                placed_once.add(spot)
                hp = next((v["header"] for v in vals if v.get("header")), "")
                layer_rows.append({k: c.get(k, "") for k in LAYER_FIELDS} | {"apply": mode, "header_place": hp})
                counts[f"text layer changes {mode}"] += 1
                if mode == "after":
                    for v in vals:
                        if any(x["entry_uid"] == uid and x["kind"] == v["kind"] and x["old_value"] == v["old_value"] and x["new_value"] == v["new_value"] for x in value_rows[-20:]):
                            continue
                        value_rows.append({"kind": v["kind"], "entry_uid": uid, "entry_id": e[0], "old_value": v["old_value"], "occurrence": "",
                                           "action": "replace", "new_value": v["new_value"], "scientific_name": v.get("scientific_name", ""),
                                           "gbif_key": v.get("gbif_key", ""), "is_bird": "", "reason": "bessere Lesung der Prüfung",
                                           "note": f"„{c['text_now']}“ → „{c['final_text']}“", "reviewed_by": c["reviewed_by"], "reviewed_at": ""})
                        counts[f"text layer value corrections ({v['kind']})"] += 1
        # signals of the corpus tiers (corpus_tiers.py); the tiers themselves are decided after the last entry
        contested = [(t[3], t[12]) for t in tcs if (t[2] or t[13]) and t[5] and ("wrong" in (t[6], t[7]) or "partly" in (t[6], t[7]))]   # also where the machine layer put the better reading: only a person settles it
        flags_e = {f["reason"] for f in qa.get(uid, [])}
        ge = g_ent.get(uid) or {}
        eg = entry_finding(ge, "g", {"date": e[2], "place": e[6], "kind": e[4]}) or {}
        ev_row = events.get(data_ns + "entry_" + uid, {})
        facts = corpus_tiers.entry_facts(
            text=text, date=ev_row.get("eventDate") or e[2] or "", kind=e[4] or "", entry_id=e[0], n_records=len(obs),
            flags_by_index={o["index"]: rec[str(o["index"])].get("g", {}).get("v") in ("wrong", "spurious") for o in obs},
            poor="transcript_poor" in flags_e, illegible=truthy(ge.get("scan_legible")) is False or "transcript_illegible" in flags_e,
            date_bad=eg.get("date_ok") is False or bool(flags_e & {"implausible_date", "date_from_position"}),
            kind_bad=eg.get("kind_ok") is False, place_bad=eg.get("place_ok") is False,
            place=ev_row.get("locality") or "", header_place=ev_row.get("verbatimLocality") or "", inserts=insert_texts.get(uid, []))
        cursor = 0
        for o in obs:
            item = rec[str(o["index"])]
            d = occ_rows.get(data_ns + "obs_" + hashlib.sha1(f"{uid}|{o['written']}|{o['index']}".encode("utf-8")).hexdigest()[:12])
            if d is None:
                continue                                      # no archive row: no tier
            name = o["written"].casefold()
            notes = o.get("notes") or ""
            a = text.find(notes, cursor) if notes else -1
            if a < 0 and notes:
                a = text.find(notes)
            if a >= 0:
                cursor = a
            # a contested correction inside the record's passage; a passage that cannot be found cannot be cleared
            touched = any(a - 2 <= pos <= a + len(notes) if a >= 0 and pos >= 0 else bool(new) and TAG.sub("", new) in TAG.sub("", notes)
                          for pos, new in contested) or (a < 0 and bool(contested))
            checks = tuple((item.get(src, {}).get("v", ""), item.get(src, {}).get("f") or []) for src in ("g", "s"))
            tiers.add(item, index=o["index"], occ=d, entry=facts, record=o, checks=checks, reading_contested=touched,
                      name_attested=form_class.get(name) == "A" or applied_taxa.get(name) == "same",
                      duplicate=d["occurrenceID"] in duplicates)
            tier_ids[(e[0], o["index"])] = d["occurrenceID"]
        # automatic changes on single records, from the QA flags
        gone = []
        for f in qa.get(uid, []):
            if f["reason"] == "value_corrected" and " -> " in f["value"]:
                frm, to = f["value"].split(" -> ", 1)
                for item in rec.values():
                    if item["w"].casefold() == to.casefold():
                        item.setdefault("auto", []).append(["value", frm, to, f["detail"]])
            elif f["reason"] == "record_corrected" and f["value"].count("|") == 2:
                w, field, to = f["value"].split("|")
                for item in rec.values():
                    if item["w"].casefold() == w.casefold():
                        item.setdefault("auto", []).append([field, "", to, f["detail"]])
            if f["action"] == "excluded":
                gone.append([f["reason"], f["value"], f["detail"]])
        miss = []
        for src, table in (("g", g_mis), ("s", {} if stale else s_mis)):
            for m in table.get(uid, []):
                miss.append({k: v for k, v in {"src": src, "kind": m.get("kind"), "text": m.get("text"), "de": m.get("species_de"),
                                               "sci": m.get("sci"), "count": m.get("count"), "loc": m.get("locality"), "date": m.get("date"),
                                               "obs": m.get("observer"), "c": fnum(m.get("confidence")), "note": m.get("note"),
                                               "in_text": 1 if m.get("text_in_entry") == "y" or (m.get("text") and plain(m["text"]) in plain(text)) else 0}.items()
                             if v not in (None, "")})
        item = {"uid": uid}
        reg = entry_regions(uid)
        if not reg:                                           # no region box: at least the pages
            reg = [[page(PG[i][0]), 0, 0, 1, 1, 1] for i in e[8]]
        fields = {"reg": reg, "tc": tcs, "qa": [[f["reason"], f["action"], f["value"], f["detail"]] for f in qa.get(uid, [])],
                  "rec": rec, "gone": gone, "miss": miss,
                  "ent": {k: v for k, v in ((src, entry_finding(table.get(uid), src, {"date": e[2], "place": e[6], "kind": e[4]}))
                                            for src, table in (("g", g_ent), ("s", s_ent))) if v},
                  "ins": inserts.get(uid, []), "media": media.get(uid, []), "chk": ("g" if g_seen else "") + ("s" if s_seen else "")}
        item.update({k: v for k, v in fields.items() if v})
        entries[e[0]] = item
        counts["entries"] += 1
        counts["entries checked (gemini)"] += g_seen
        counts["entries checked (sonnet)"] += s_seen
        for src in ("g", "s"):
            counts[f"records flagged ({src})"] += sum(1 for r in rec.values() if r.get(src, {}).get("v") in ("wrong", "spurious"))
        counts["missing records suggested"] += sum(1 for m in miss if m.get("kind") == "observation")

    if args.machine_text_layer:
        out = Path(args.machine_text_layer)
        out.mkdir(parents=True, exist_ok=True)
        for name, fields, rows in (("text_layer_machine.csv", LAYER_FIELDS, layer_rows),
                                   ("value_corrections_text_machine.csv", ["kind", "entry_uid", "entry_id", "old_value", "occurrence", "action",
                                                                           "new_value", "scientific_name", "gbif_key", "is_bird", "reason", "note",
                                                                           "reviewed_by", "reviewed_at"], value_rows)):
            with open(out / name, "w", encoding="utf-8", newline="") as h:
                w = csv.DictWriter(h, fieldnames=fields)
                w.writeheader()
                w.writerows(rows)
            print(f"{out / name}: {len(rows)} rows")

    # ------------------------------------------------------------ corpus tiers (needs every record: place doubt)
    if args.dwca:
        counts.update(tiers.assign())
        if args.tiers_csv:
            corpus_tiers.write_csv(args.tiers_csv, corpus_tiers.tier_rows(entries, tier_ids))
            print(f"{args.tiers_csv}: {len(tier_ids)} records")

    # ------------------------------------------------------------ estimated quality per record (replaces the corpus tiers)
    quality_summary = None
    if args.quality:
        qdir = Path(args.quality)
        short = {"exists": "ex", "species": "sp", "count": "n", "date": "d", "place": "pl", "observer": "ob", "record_type": "ty"}
        for r in csv.DictReader(open(qdir / "record_quality.csv", encoding="utf-8", newline="")):
            item = entries.get(r["entry_id"], {}).get("rec", {}).get(r["obs_index"])
            if item is None:
                counts["quality rows without a record"] += 1
                continue
            q = {"p": round(float(r["p_any"]), 3), "po": round(float(r["p_occurrence"]), 3),
                 "pc": round(float(r["p_coords"]), 3) if r["p_coords"] else None, "lv": int(r["level"]),
                 "s": [r[f"s_{f}"] for f in short] + [r["s_coords"]],
                 "pf": [round(float(r[f"p_{f}"]), 3) for f in short],
                 "x": {k: r[f"check_{f}"] for f, k in short.items() if r.get(f"check_{f}")}}
            item["q"] = {k: v for k, v in q.items() if v not in (None, {})}
            counts["records with a quality estimate"] += 1
        for item in (rv for e in entries.values() for rv in e.get("rec", {}).values()):
            item.pop("t", None)
            item.pop("tw", None)
        quality_summary = json.loads((qdir / "quality_summary.json").read_text(encoding="utf-8"))

    # ------------------------------------------------------------ names: machine rows, link before / now
    names: dict = {}

    def links(payload):
        out = {}
        if not payload:
            return out
        for sec, key, pick in (("taxa", "taxon", lambda en: [en[0], en[1], en[2]]),
                               ("persons", "person", lambda en: [en[0], en[1], en[2]]),
                               ("places", "place", lambda en: [en[0], en[1], en[2], en[4], en[5], en[7]]),
                               ("habitats", "habitat", lambda en: [en[0], en[1], en[2]])):
            for f in payload[key]["forms"]:
                out[f"{sec}|{f[0].casefold()}"] = pick(payload[key]["ent"][f[2]])
        return out

    def identity(key, link):
        """What makes two links of a name the same link (labels, rounding and source wording do not)."""
        sec = key.split("|", 1)[0]
        if sec == "taxa":
            return (str(link[2] or ""),) if link[2] else ("", (link[1] or "").casefold())
        if sec == "places":
            return (round(float(link[1]), 3) if link[1] is not None else None,
                    round(float(link[2]), 3) if link[2] is not None else None, str(link[3] or ""), str(link[4] or ""))
        return tuple(str(x or "") for x in link[1:])

    now, before = links(P), links(load_payload(args.payload_before) if args.payload_before else None)
    if args.machine:
        for r in read_csv(Path(args.machine) / "identities_machine.csv"):
            conf, agree = fnum(r.get("confidence")) or 0.0, int(float(r.get("agreement") or 0))
            auto = 1 if conf >= args.min_confidence and agree >= args.min_agreement else 0
            row = {k: v for k, v in {"n": r["name_form"], "d": r["decision"], "t": r.get("target"), "auth": r.get("authority"),
                                     "sci": r.get("scientific_name"), "rank": r.get("rank"), "lat": r.get("lat"), "lon": r.get("lon"),
                                     "unc": r.get("uncertainty_m"), "eunis": r.get("eunis_match"),
                                     "c": conf, "ag": agree, "src": r.get("sources"), "rnd": r.get("round"), "why": r.get("reason"),
                                     "note": r.get("note"), "auto": auto}.items() if v not in (None, "")}
            key = f"{r['section']}|{r['name_form'].casefold()}"
            entry = names.setdefault(key, {})
            entry.setdefault("rows", []).append(row)
            if key in now:
                entry.setdefault("now", now[key])
                # the link without the machine review, where an applied row changed it (other differences
                # between the two exports are run-to-run noise of the linking models, not decisions)
                if auto and before.get(key) is not None and identity(key, before[key]) != identity(key, now[key]) \
                        and "before" not in entry:
                    entry["before"] = before[key]
                    counts["names changed by the machine review"] += 1
            counts["machine rows"] += 1
            counts["machine rows applied"] += auto

    out = {"meta": {"export": P.get("export"), "built": datetime.date.today().isoformat(),
                    "thresholds": {"confidence": args.min_confidence, "agreement": args.min_agreement}, "counts": dict(counts)},
           "pages": pages, "entries": entries, "names": names, "crops": crops, "regions": regions}
    if quality_summary:
        out["meta"]["quality"] = quality_summary
    out["meta"]["counts"]["regions with a crop"] = sum(len(v) for v in media.values())
    out["meta"]["counts"]["crops with a Drive id"] = len(crops)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(dict(counts), indent=1))
    print(f"{args.out}: {Path(args.out).stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
