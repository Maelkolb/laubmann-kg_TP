#!/usr/bin/env python3
"""Apply reviewed entry boundaries to a (deduplicated) corpus.

Reads ``corpus.json`` + ``entries.csv`` of the input corpus and a boundary CSV
(laubmann_corpus/boundaries.py: ``start`` = a missed entry header, ``stop`` =
the entry before ends here, e.g. where a volume's register begins) and writes
a new corpus directory with regenerated ``entries.csv`` / ``entries.jsonl``,
``corpus.json`` (entry_starts include the boundary headers, ``entry_stops``
the stops) and ``boundaries_report.csv``. The input corpus is never modified.

Identity is preserved: the stream text is unchanged, so every entry_uid of the
input corpus is reproduced; existing entries keep their ``entry_id`` and new
entries get the id of the entry before them plus a letter (``L05-e0123a``), so
sample ranges, value corrections and the gold set keep pointing at the same
entries. Every entry lists the body-text regions it runs through
(``source_regions``, JSON) — the continuation pages of a long entry are part
of the graph that way. An undated boundary header is dated by position (the
date of the entry before it; ``year_form`` = positional).

``--mask`` (CSV region_uid[, reason]) blanks regions out of the entry text:
body-text regions whose transcription is known to be unreliable (the regions
the multimodal cleaning removed — faint bleed-through readings of folded
slips, repetition loops, gibberish — and the paragraphs that are really maps
or photographs) or irrelevant (the back of a clipping: advertisements, local
news). The text is replaced by blanks of the same length, so stream offsets
and entry_uids do not move; an entry whose header lies in a masked region has
no text left and is dropped (reported), a boundary start inside a masked
region is not applied.

Usage:
    python dedup/apply_entry_boundaries.py --corpus-dir data/corpus_dedup \\
        --boundaries data/corpus_patches/entry_boundaries.csv \\
        --mask data/corpus_patches/masked_regions.csv \\
        --out-dir data/corpus_patched
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import string
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

_HERE = Path(__file__).resolve().parent
for _p in (_HERE, _HERE.parent):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from laubmann_corpus.boundaries import apply_boundaries, load_boundaries  # noqa: E402
from laubmann_corpus.ids import page_uid as _page_uid  # noqa: E402
from laubmann_corpus.loading import ENTRY_SCAN_TYPES  # noqa: E402
from laubmann_corpus.stream import _assign_entry_uids, annotate_pages, segment_entries  # noqa: E402

csv.field_size_limit(10 * 1024 * 1024)

ENTRY_COLS = ["entry_id", "volume", "scan", "page_id", "image", "region_id", "region_type",
              "reading_order", "date_raw", "date_norm", "year", "location_raw", "variant",
              "n_chars", "n_words", "preview", "text_clean", "entry_uid", "page_uid",
              "region_uid", "month_source", "year_form", "loc_source",
              "source_regions", "boundary_source", "boundary_kind", "context_before"]

# entries split off at a boundary of these kinds get the tail of the text
# before them as read-only context for the extraction model: a pasted report
# is introduced by the diarist ("Bericht von E. Bezzel vom 19. X.:") and
# without that line its "ich" reads as the diarist. Digests and resumptions
# get none: they need no attribution help, and the A/B test showed the model
# re-extracting travel from a resumption's context.
CONTEXT_KINDS = {"correspondence", "retrospective", "other"}
CONTEXT_SOURCES: set = set()
CONTEXT_CHARS = 1200


def _pages_by_volume(pages: List[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
    """Same ordering and region flags as apply_dedup._regenerate_entries_stream."""
    by_vol: Dict[int, List[Dict[str, Any]]] = {}
    for p in copy.deepcopy(pages):
        by_vol.setdefault(int(p["volume"]), []).append(p)
    for vol, vpages in by_vol.items():
        vpages.sort(key=lambda p: (int(p.get("scan", 0)), p["page_id"]))
        for page in vpages:
            page.setdefault("page_uid", _page_uid(vol, page["page_id"]))
            page.setdefault("image", f"{page['page_id']}.png")
            for reg in page.get("regions", []):
                reg.setdefault("id", reg.get("region_id", ""))
                reg.setdefault("type", reg.get("region_type", ""))
                reg.setdefault("reading_order", None)
                reg.setdefault("region_uid", "")
                reg.setdefault("text", "")
                reg["scan_entries"] = reg["type"] in ENTRY_SCAN_TYPES and bool(reg["text"])
        annotate_pages(vpages, vol, loose=False)
    return by_vol


def _suffix(n: int) -> str:
    letters = string.ascii_lowercase
    out = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        out = letters[r] + out
    return out


def _mask_text(text: str) -> str:
    """Blank a region's text without changing its length (offsets stay valid)."""
    return "".join(c if c == "\n" else " " for c in text)


def regenerate(pages: List[Dict[str, Any]], boundary_rows: List[Dict[str, str]],
               old_ids: Dict[str, str], masked: Dict[str, str] | None = None
               ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[int, List[Dict[str, Any]]]]:
    masked = masked or {}
    by_vol = _pages_by_volume(pages)
    report = apply_boundaries(by_vol, boundary_rows)
    # a boundary start inside a masked region is not applied
    for vpages in by_vol.values():
        for p in vpages:
            for reg in p["regions"]:
                if reg.get("region_uid") not in masked or not reg.get("starts"):
                    continue
                for h in reg["starts"]:
                    if h.get("variant") != "boundary":
                        continue
                    for r in report:
                        if (r["status"] == "applied" and r["page_id"] == p["page_id"]
                                and r["region_id"] == reg["id"] and r["line"].rstrip() == h["header_line"].rstrip()):
                            r["status"] = "masked"
                reg["starts"] = [h for h in reg["starts"] if h.get("variant") != "boundary"]
    entries: List[Dict[str, Any]] = []
    for vol in sorted(by_vol):
        vpages = by_vol[vol]
        _assign_entry_uids(vpages, vol)
        for p in vpages:                         # blank after uid assignment: offsets unchanged
            for reg in p["regions"]:
                if reg.get("region_uid") in masked:
                    reg["orig_text"] = reg["text"]
                    reg["text"] = _mask_text(reg["text"])
                    reg["masked"] = masked[reg["region_uid"]]
        hits = {h["entry_uid"]: h for p in vpages for r in p["regions"] for h in r.get("starts", [])}
        prev_id = f"L{vol:02d}-e0000"
        prev_date = None
        prev_text = ""
        used: Counter = Counter()
        for e in segment_entries(vol, vpages):
            h = hits.get(e["entry_uid"], {})
            if not e["text_clean"].strip():
                e["dropped"] = "masked-header"      # header in a masked region: nothing reliable left
            if e["entry_uid"] in old_ids:
                e["entry_id"] = old_ids[e["entry_uid"]]
                prev_id = e["entry_id"]
            else:
                e["entry_id"] = f"{prev_id}{_suffix(used[prev_id])}"
                used[prev_id] += 1
            e["boundary_source"] = h.get("boundary_source") or ""
            e["boundary_kind"] = h.get("boundary_kind") or ""
            if h.get("variant") == "boundary" and not e.get("date_norm") and prev_date:
                e["date_norm"] = prev_date            # dated by position (flagged by year_form)
                e["year"] = int(prev_date[:4])
            if e.get("date_norm"):
                prev_date = e["date_norm"]
            e["context_before"] = ""
            if h.get("variant") == "boundary" and (e["boundary_kind"] in CONTEXT_KINDS
                                                  or e["boundary_source"] in CONTEXT_SOURCES):
                tail = prev_text[-CONTEXT_CHARS:]
                e["context_before"] = ("…" + tail[tail.find(" ") + 1:]) if len(prev_text) > CONTEXT_CHARS else tail
            if not e.get("dropped"):
                prev_text = e["text_clean"]
            e["source_regions"] = json.dumps(e.get("source_regions") or [], ensure_ascii=False)
            e["preview"] = (e["text_clean"][:120] + "…") if len(e["text_clean"]) > 120 else e["text_clean"]
            entries.append(e)
    dropped = {e["entry_uid"] for e in entries if e.get("dropped")}
    for vpages in by_vol.values():               # later stages (multimodal relink) must not see them
        for p in vpages:
            for reg in p["regions"]:
                if reg.get("starts"):
                    reg["starts"] = [h for h in reg["starts"] if h.get("entry_uid") not in dropped]
    by_uid = {e["entry_uid"]: e for e in entries}
    for r in report:
        r["entry_uid"] = ""
    for vol, vpages in by_vol.items():
        for p in vpages:
            for reg in p["regions"]:
                for h in reg.get("starts", []):
                    if h.get("variant") == "boundary":
                        for r in report:
                            if (r["status"] == "applied" and r["action"] == "start" and int(r["volume"]) == vol
                                    and r["page_id"] == p["page_id"] and r["region_id"] == reg["id"]
                                    and r["line"].rstrip() == h["header_line"].rstrip()):
                                r["entry_uid"] = h["entry_uid"]
                                r["entry_id"] = by_uid.get(h["entry_uid"], {}).get("entry_id", "")
    return entries, report, by_vol


def _corpus_json(by_vol: Dict[int, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """corpus.json with the boundary headers in entry_starts and the stops in
    entry_stops (working keys removed)."""
    out = []
    for vol in sorted(by_vol):
        for p in by_vol[vol]:
            q = {k: v for k, v in p.items()}
            regs = []
            for reg in p["regions"]:
                r = {k: v for k, v in reg.items() if k not in ("starts", "stops", "scan_entries", "orig_text")}
                if reg.get("masked"):
                    r["text"] = reg["orig_text"]          # corpus.json keeps the transcription
                    r["masked"] = reg["masked"]
                r["entry_starts"] = [{k: v for k, v in h.items() if k not in ("end", "header_line")}
                                     for h in reg.get("starts", [])]
                if reg.get("stops"):
                    r["entry_stops"] = list(reg["stops"])
                regs.append(r)
            q["regions"] = regs
            out.append(q)
    return out


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus-dir", required=True, type=Path)
    ap.add_argument("--boundaries", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--mask", type=Path, help="CSV region_uid[,reason]: regions blanked out of the entry text")
    args = ap.parse_args(argv)

    pages = json.loads((args.corpus_dir / "corpus.json").read_text(encoding="utf-8"))
    with (args.corpus_dir / "entries.csv").open(newline="", encoding="utf-8") as fh:
        old = list(csv.DictReader(fh))
    old_ids = {r["entry_uid"]: r["entry_id"] for r in old}
    old_text = {r["entry_uid"]: r["text_clean"] for r in old}
    rows = load_boundaries(args.boundaries)
    masked: Dict[str, str] = {}
    if args.mask:
        with args.mask.open(newline="", encoding="utf-8") as fh:
            masked = {r["region_uid"]: (r.get("reason") or "masked") for r in csv.DictReader(fh)}

    entries, report, by_vol = regenerate(pages, rows, old_ids, masked)
    dropped_entries = [e for e in entries if e.get("dropped")]
    entries = [e for e in entries if not e.get("dropped")]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    with (args.out_dir / "entries.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=ENTRY_COLS, extrasaction="ignore")
        w.writeheader()
        for e in entries:
            w.writerow(e)
    with (args.out_dir / "entries.jsonl").open("w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps({k: e.get(k) for k in ENTRY_COLS + ["text_raw", "stream_start", "stream_end"]},
                                ensure_ascii=False) + "\n")
    (args.out_dir / "corpus.json").write_text(json.dumps(_corpus_json(by_vol), ensure_ascii=False),
                                              encoding="utf-8")
    report_cols = ["status", "entry_id", "entry_uid"] + [c for c in rows[0].keys()] if rows else ["status"]
    with (args.out_dir / "boundaries_report.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=report_cols, extrasaction="ignore")
        w.writeheader()
        for r in report:
            w.writerow(r)

    new_uids = {e["entry_uid"] for e in entries}
    kept = [e for e in entries if e["entry_uid"] in old_ids]
    changed = sum(1 for e in kept if e["text_clean"] != old_text[e["entry_uid"]])
    summary = {
        "input_entries": len(old),
        "output_entries": len(entries),
        "new_entries": len(entries) - len(kept),
        "lost_entries": len(set(old_ids) - new_uids - {e["entry_uid"] for e in dropped_entries}),
        "dropped_masked_header_entries": len(dropped_entries),
        "dropped_masked_header_entry_ids": sorted(e["entry_id"] for e in dropped_entries if e["entry_uid"] in old_ids),
        "masked_regions": len(masked),
        "existing_entries_with_changed_text": changed,
        "boundaries": dict(Counter(f"{r['action']}:{r['status']}" for r in report)),
    }
    (args.out_dir / "boundaries_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if summary["lost_entries"]:
        print("ERROR: entries of the input corpus disappeared (other than masked-header entries)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
