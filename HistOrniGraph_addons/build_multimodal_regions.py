#!/usr/bin/env python3
"""Build ``multimodal_regions.jsonl``: the graph's lkg:MultimodalRegion input.

Sources (cleaned multimodal catalogue v2, 2026-08-18):
  * ``multimodal_v2_images.jsonl`` — drawings, sketch maps, photographs,
    postcards, prints and mounted objects (1,420 regions),
  * ``text_inserts_v2.jsonl`` — reliable text regions; only paragraphs and
    lists the review judged relevant are taken (``--insert-decisions``, column
    decision keep|drop), marginal notes never.

Two fixes make them usable in the graph:

1. **Duplicates.** Pages scanned more than once (mostly on adjacent scans)
   carry the same photo/map/insert twice. ``--duplicates`` (region_uid,
   duplicate_of, …) removes every region that duplicates a kept one;
   ``detect_image_duplicates`` produces the automatic part of that table.
2. **Entry links.** The catalogue's ``entry_uid`` was computed on the corpus
   before deduplication, which regenerated the entry uids (only a few percent
   still resolve). Each region is relinked to the entry of the corpus the
   graph is built from, with the catalogue builder's own rule: the nearest
   entry header preceding the region in reading order (volume pages ordered by
   scan, regions of a page by reading order); a reviewed stop (the start of a
   register) ends the current entry. The corpus is the patched one
   (dedup/apply_entry_boundaries.py), whose corpus.json carries the boundary
   headers and stops. Deduplication moved some text pages away from the image
   page facing them (a rescan's copy was kept on a neighbouring scan), so the
   walk can land one day early; when ``--catalogue-entries`` (the pre-dedup
   entries.csv the catalogue was built on) is given, the catalogue's own link,
   mapped to this corpus by volume + date + place (+ text start), wins unless
   the walk found a boundary entry (a header the catalogue never knew).

Usage:
    python build_multimodal_regions.py --corpus-dir data/corpus_patched \\
        --catalogue-dir ~/Downloads/multimodal_catalogue_v2_2026-08-18 \\
        --reading-order data/corpus_dedup/multimodal_clean.md \\
        --insert-decisions data/corpus_patches/text_insert_decisions.csv \\
        --duplicates data/corpus_patches/multimodal_duplicates.csv \\
        --out data/corpus_patched/multimodal_regions.jsonl
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

REGION_KINDS = ("drawing", "photograph", "map", "print", "object", "text-insert", "list")
_MM_COMMENT = re.compile(r"<!--\s*mm\s+(.*?)-->", re.S)
_KV = re.compile(r"(\w+)=([^\s]*)")


# --------------------------------------------------------------------------
# kind
# --------------------------------------------------------------------------

def region_kind(rec: Dict[str, Any]) -> str:
    """lkg:regionKind from the layout type, the review's reclassification kind
    and the first sentence of the model's description."""
    rtype = rec.get("type_original") or rec.get("region_type") or ""
    if rtype == "ListRegion":
        return "list"
    if rec.get("class") == "text" or (rtype in ("ParagraphRegion", "MarginaliaRegion") and not rec.get("reclassified")):
        return "text-insert"
    if rtype == "ObjectRegion":
        return "object"
    kind = (rec.get("kind") or "").lower()
    first = (rec.get("description") or "").split(".")[0].lower()
    for words, value in ((("map", "panorama"), "map"), (("photo", "postcard"), "photograph"),
                         (("print", "painting", "engraving"), "print"),
                         (("leaf", "feather", "label", "card", "ticket", "stamp"), "object")):
        if any(w in kind for w in words):
            return value
    if re.search(r"\bmap\b|panoram", first):
        return "map"
    if re.search(r"photograph|photo\b|postcard", first):
        return "photograph"
    if re.search(r"engraving|lithograph|\bprint\b|printed|painting", first):
        return "print"
    if re.search(r"feather|leaf|leaves|pressed|specimen|flower|plant|stamp|label|ticket|tape|envelope", first):
        return "object"
    return "drawing"


# --------------------------------------------------------------------------
# reading-order walk
# --------------------------------------------------------------------------

def reading_orders(md_path: Path) -> Dict[str, int]:
    """region_uid -> reading order on its page, from the catalogue markdown's
    <!-- mm ... order=N ... --> comments."""
    out: Dict[str, int] = {}
    for m in _MM_COMMENT.finditer(md_path.read_text(encoding="utf-8")):
        kv = dict(_KV.findall(m.group(1)))
        if kv.get("region_uid") and str(kv.get("order", "")).lstrip("-").isdigit():
            out[kv["region_uid"]] = int(kv["order"])
    return out


def relink(corpus_pages: List[Dict[str, Any]], regions: List[Dict[str, Any]],
           order: Dict[str, int]) -> Dict[str, Optional[str]]:
    """region_uid -> entry_uid of the nearest preceding entry header in reading
    order (None before the first header of a volume or after a stop)."""
    by_vol: Dict[int, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    for p in corpus_pages:
        by_vol[int(p["volume"])][p["page_id"]] = {"scan": int(p.get("scan") or 0), "page_id": p["page_id"],
                                                   "body": p["regions"], "mm": []}
    for r in regions:
        vol = int(r["volume"])
        page = by_vol[vol].setdefault(r["page_id"], {"scan": int(r.get("scan") or 0), "page_id": r["page_id"],
                                                     "body": [], "mm": []})
        page["mm"].append(r)
    out: Dict[str, Optional[str]] = {}
    for vol, pages in by_vol.items():
        current: Optional[str] = None
        for page in sorted(pages.values(), key=lambda p: (p["scan"], p["page_id"])):
            seq: List[Tuple[int, int, str, Any]] = []
            for reg in page["body"]:
                ro = reg.get("reading_order") or 0
                # stops and starts inside one body region, in text order
                marks = [(h["offset"], "start", h.get("entry_uid")) for h in reg.get("entry_starts", [])]
                marks += [(off, "stop", None) for off in reg.get("entry_stops", [])]
                for off, what, uid in sorted(marks, key=lambda x: x[0]):
                    seq.append((ro, 0, what, uid))
            for r in page["mm"]:
                seq.append((order.get(r["region_uid"], 10**6), 1, "mm", r["region_uid"]))
            for _, _, what, value in sorted(seq, key=lambda x: (x[0], x[1])):
                if what == "start":
                    current = value
                elif what == "stop":
                    current = None
                else:
                    out[value] = current
    return out


# --------------------------------------------------------------------------
# duplicates
# --------------------------------------------------------------------------

def _dhash(path: Path, n: int = 8) -> int:
    from PIL import Image  # optional dependency, only for detection
    im = Image.open(path).convert("L").resize((n + 1, n), Image.LANCZOS)
    px = list(im.getdata())
    bits = 0
    for r in range(n):
        for c in range(n):
            bits = (bits << 1) | (1 if px[r * (n + 1) + c] > px[r * (n + 1) + c + 1] else 0)
    return bits


def _side(page_id: str) -> str:
    s = page_id.rsplit("_", 1)[-1]
    return s if s in ("L", "R") else "S"


def detect_image_duplicates(images: List[Dict[str, Any]], thumbs_dir: Path,
                            rescan_pairs: Iterable[Tuple[int, int, int]] = (),
                            max_scan_gap: int = 2) -> List[Dict[str, Any]]:
    """Automatic duplicate pairs among image/object regions: same volume, at most
    ``max_scan_gap`` scans apart, similar aspect ratio (0.8–1.25) and a small
    difference hash of the catalogue thumbnail (≤ 10 bits; ≤ 16 when the text
    dedup already paired the two scans as rescans of one page). A page seen as
    two halves and as a full spread (``_0140_L`` / ``_0140``) counts as
    adjacent. Returns rows region_uid, duplicate_of, method, hamming, note —
    the second region of a pair (later scan) is the duplicate."""
    rescans = {(v, min(a, b), max(a, b)) for v, a, b in rescan_pairs}
    hashes = {}
    for r in images:
        path = thumbs_dir / f"{r['region_uid']}.png"
        if path.exists():
            hashes[r["region_uid"]] = _dhash(path)
    rows = []
    by_vol: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for r in images:
        if r["region_uid"] in hashes:
            by_vol[int(r["volume"])].append(r)
    for vol, rs in by_vol.items():
        rs.sort(key=lambda r: (int(r["scan"]), r["page_id"]))
        for i, a in enumerate(rs):
            for b in rs[i + 1:]:
                gap = int(b["scan"]) - int(a["scan"])
                if gap > max_scan_gap:
                    break
                if a["page_id"] == b["page_id"]:
                    continue
                ar = (a["width"] / a["height"]) / (b["width"] / b["height"])
                if not 0.8 <= ar <= 1.25:
                    continue
                ham = bin(hashes[a["region_uid"]] ^ hashes[b["region_uid"]]).count("1")
                rescan = (vol, int(a["scan"]), int(b["scan"])) in rescans
                if ham <= 10 or (rescan and ham <= 16):
                    rows.append({"region_uid": b["region_uid"], "duplicate_of": a["region_uid"],
                                 "method": "auto-dhash" + ("+rescan" if rescan else ""), "hamming": ham,
                                 "note": f"vol {vol} scan {a['scan']}/{b['scan']}"})
    return rows


def load_duplicates(path: Optional[Path]) -> Dict[str, str]:
    """region_uid -> the region it duplicates (rows with decision n are ignored),
    resolved to the cluster's kept region."""
    if not path or not Path(path).exists():
        return {}
    dup: Dict[str, str] = {}
    with Path(path).open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if (row.get("decision") or "y").strip().lower() in ("n", "no", "0", "reject"):
                continue
            if row.get("region_uid") and row.get("duplicate_of"):
                dup[row["region_uid"]] = row["duplicate_of"]
    def root(u: str) -> str:
        seen = set()
        while u in dup and u not in seen:
            seen.add(u)
            u = dup[u]
        return u
    return {u: root(u) for u in dup}


def load_insert_decisions(path: Optional[Path]) -> Dict[str, str]:
    if not path or not Path(path).exists():
        return {}
    with Path(path).open(newline="", encoding="utf-8") as fh:
        return {r["region_uid"]: (r.get("decision") or "").strip().lower() for r in csv.DictReader(fh)}


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------

def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def map_catalogue_entries(catalogue_entries: List[Dict[str, str]],
                          corpus_entries: List[Dict[str, str]]) -> Dict[str, str]:
    """Pre-dedup entry_uid -> entry_uid of this corpus, by volume + date_raw +
    location_raw + the first 150 characters of text, else volume + date_raw +
    location_raw when that is unique."""
    def k3(r):
        return (str(r["volume"]), (r.get("date_raw") or "").strip(), (r.get("location_raw") or "").strip())
    n4: Dict[tuple, List[str]] = defaultdict(list)
    n3: Dict[tuple, List[str]] = defaultdict(list)
    for r in corpus_entries:
        n4[k3(r) + ((r.get("text_clean") or "")[:150],)].append(r["entry_uid"])
        n3[k3(r)].append(r["entry_uid"])
    out: Dict[str, str] = {}
    for r in catalogue_entries:
        cand = n4.get(k3(r) + ((r.get("text_clean") or "")[:150],)) or []
        if len(cand) != 1:
            cand = n3.get(k3(r)) or []
        if len(cand) == 1:
            out[r["entry_uid"]] = cand[0]
    return out


def build(corpus_pages: List[Dict[str, Any]], images: List[Dict[str, Any]], inserts: List[Dict[str, Any]],
          order: Dict[str, int], insert_decisions: Dict[str, str],
          duplicates: Dict[str, str], catalogue_map: Optional[Dict[str, str]] = None,
          boundary_entries: Iterable[str] = ()) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    stats: Counter = Counter()
    selected: List[Dict[str, Any]] = []
    for r in images:
        selected.append(dict(r, source="images-v2"))
    for r in inserts:
        if r.get("type_original") == "MarginaliaRegion":
            stats["insert_marginalia_excluded"] += 1
            continue
        if insert_decisions.get(r["region_uid"], "drop" if insert_decisions else "keep") != "keep":
            stats["insert_not_selected"] += 1
            continue
        selected.append(dict(r, source="text-inserts"))
    kept = []
    for r in selected:
        if r["region_uid"] in duplicates:
            stats[f"duplicate_removed_{r['source']}"] += 1
            continue
        kept.append(r)
    links = relink(corpus_pages, kept, order)
    catalogue_map = catalogue_map or {}
    boundary_entries = set(boundary_entries)
    out = []
    for r in kept:
        entry_uid = links.get(r["region_uid"])
        link_method = "reading-order"
        mapped = catalogue_map.get(r.get("entry_uid") or "")
        if mapped and mapped != entry_uid and entry_uid not in boundary_entries:
            entry_uid, link_method = mapped, "catalogue"
            stats["link_from_catalogue"] += 1
        if entry_uid is None:
            stats[f"no_entry_{r['source']}"] += 1
        stats[f"kept_{r['source']}"] += 1
        stats["catalogue_link_changed"] += int(bool(r.get("entry_uid")) and entry_uid != r.get("entry_uid"))
        out.append({
            "region_uid": r["region_uid"], "page_uid": r["page_uid"], "page_id": r["page_id"],
            "volume": int(r["volume"]), "scan": int(r["scan"]),
            "entry_uid": entry_uid or "", "entry_uid_catalogue": r.get("entry_uid") or "",
            "region_type": r.get("type_original") or "", "kind": region_kind(r),
            "reading_order": order.get(r["region_uid"]),
            "description": r.get("description") or "", "visible_text": r.get("visible_text") or "",
            "crop": r.get("crop") or "", "source": r["source"], "link_method": link_method,
        })
    stats["regions_with_entry"] = sum(1 for r in out if r["entry_uid"])
    stats.update(Counter(f"kind_{r['kind']}" for r in out if r["entry_uid"]))
    return out, dict(stats)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus-dir", required=True, type=Path, help="patched corpus (corpus.json)")
    ap.add_argument("--catalogue-dir", required=True, type=Path,
                    help="multimodal_catalogue_v2 folder (multimodal_v2_images.jsonl, text_inserts_v2.jsonl)")
    ap.add_argument("--reading-order", required=True, type=Path, help="multimodal_clean.md (order= per region)")
    ap.add_argument("--insert-decisions", type=Path, help="CSV region_uid,decision (keep|drop)")
    ap.add_argument("--duplicates", type=Path, help="CSV region_uid,duplicate_of[,decision]")
    ap.add_argument("--catalogue-entries", type=Path,
                    help="pre-dedup entries.csv the catalogue's entry_uid refers to (optional)")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)

    pages = json.loads((args.corpus_dir / "corpus.json").read_text(encoding="utf-8"))
    images = _read_jsonl(args.catalogue_dir / "multimodal_v2_images.jsonl")
    inserts = _read_jsonl(args.catalogue_dir / "text_inserts_v2.jsonl")
    csv.field_size_limit(10 * 1024 * 1024)
    with (args.corpus_dir / "entries.csv").open(newline="", encoding="utf-8") as fh:
        corpus_entries = list(csv.DictReader(fh))
    catalogue_map: Dict[str, str] = {}
    if args.catalogue_entries:
        with args.catalogue_entries.open(newline="", encoding="utf-8") as fh:
            catalogue_map = map_catalogue_entries(list(csv.DictReader(fh)), corpus_entries)
    boundary_entries = [r["entry_uid"] for r in corpus_entries if r.get("boundary_source")]
    rows, stats = build(pages, images, inserts, reading_orders(args.reading_order),
                        load_insert_decisions(args.insert_decisions), load_duplicates(args.duplicates),
                        catalogue_map, boundary_entries)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps(stats, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
